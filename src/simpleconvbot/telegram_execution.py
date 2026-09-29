from __future__ import annotations

import logging
from asyncio import to_thread
from dataclasses import dataclass
from pathlib import Path
from time import monotonic

from aiogram import Bot
from aiogram.types import FSInputFile, Message

from simpleconvbot.image_engine import (
    CompressionPreset,
    ImageEngine,
    ImageOutputFormat,
    ImageTransform,
)
from simpleconvbot.jobs import JobAdmissionRejected, JobSnapshot
from simpleconvbot.localization import Locale, UserErrorCode, error_text, operation_title
from simpleconvbot.media_engine import (
    AudioOutputFormat,
    MediaEngine,
    VideoCompressionPreset,
)
from simpleconvbot.operations import OperationDefinition
from simpleconvbot.pdf_engine import PdfEngine, PdfEngineError, PdfErrorCode
from simpleconvbot.ports import DeliveryPort, ExecutionResult, OperationExecutor
from simpleconvbot.redis_security import RedisUpdateRateLimiter
from simpleconvbot.services import JobService, StartJobRequest
from simpleconvbot.storage import LocalTemporaryStorage
from simpleconvbot.telemetry import (
    OperationOutcome,
    OperationStage,
    TelemetryEvent,
    TelemetryEventType,
    emit_telemetry,
    opaque_correlation_id,
)

LOGGER = logging.getLogger(__name__)
INPUT_NAME = "input"
TELEGRAM_MAX_RENDERED_PDF_PAGES = 20


class UserFacingError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class TelegramFile:
    file_id: str
    file_size: int | None


def message_file(message: Message) -> TelegramFile | None:
    """Return the safely addressable source attachment from a user message."""
    if message.photo:
        photo = message.photo[-1]
        return TelegramFile(photo.file_id, photo.file_size)
    if message.document is not None:
        return TelegramFile(message.document.file_id, message.document.file_size)
    if message.audio is not None:
        return TelegramFile(message.audio.file_id, message.audio.file_size)
    if message.video is not None:
        return TelegramFile(message.video.file_id, message.video.file_size)
    return None


def image_operation(callback_data: str | None) -> str | None:
    if callback_data is None:
        return None
    return {
        "ui:image:jpg": "image.to_jpeg",
        "ui:image:png": "image.to_png",
        "ui:image:webp": "image.to_webp",
        "ui:image:compress": "image.compress",
    }.get(callback_data)


def pdf_operation(callback_data: str | None) -> str | None:
    if callback_data == "ui:pdf:png":
        return "pdf.to_images"
    return None


def audio_operation(callback_data: str | None) -> str | None:
    if callback_data is None:
        return None
    return {
        "ui:audio:mp3": "audio.to_mp3",
        "ui:audio:m4a": "audio.to_m4a",
        "ui:audio:wav": "audio.to_wav",
    }.get(callback_data)


def video_operation(callback_data: str | None) -> str | None:
    if callback_data is None:
        return None
    return {
        "ui:video:mp3": "video.to_mp3",
        "ui:video:mute": "video.mute",
        "ui:video:gif": "video.to_gif",
        "ui:video:compress": "video.compress",
    }.get(callback_data)


class TelegramImageExecutor(OperationExecutor):
    def __init__(self, storage: LocalTemporaryStorage, engine: ImageEngine | None = None) -> None:
        self._storage = storage
        self._engine = engine or ImageEngine()

    async def execute(
        self,
        job: JobSnapshot,
        operation: OperationDefinition,
        workspace: Path,
    ) -> ExecutionResult:
        started = monotonic()
        if operation.worker_family != "image":
            raise UserFacingError(UserErrorCode.INTERNAL_ERROR.value)
        try:
            source = await self._storage.workspace_file(job.job_id, INPUT_NAME)
            target_format, preset = _image_request(operation.operation_id)
            suffix = target_format.value.lower().replace("jpeg", "jpg")
            destination = await self._storage.workspace_file(job.job_id, f"result.{suffix}")
            await to_thread(
                self._engine.transform,
                source,
                destination,
                ImageTransform(target_format=target_format, compression=preset),
            )
            await self._storage.enforce_quota(job.job_id)
        except Exception as exc:
            _emit_failure(job, started, exc)
            raise
        _emit(job, OperationStage.WORKER, OperationOutcome.SUCCESS, started)
        return ExecutionResult(output_ref=str(destination))


class TelegramPdfExecutor(OperationExecutor):
    def __init__(self, storage: LocalTemporaryStorage, engine: PdfEngine | None = None) -> None:
        self._storage = storage
        self._engine = engine or PdfEngine()

    async def execute(
        self,
        job: JobSnapshot,
        operation: OperationDefinition,
        workspace: Path,
    ) -> ExecutionResult:
        started = monotonic()
        if operation.worker_family != "pdf" or operation.operation_id != "pdf.to_images":
            raise UserFacingError(UserErrorCode.INTERNAL_ERROR.value)

        try:
            source = await self._storage.workspace_file(job.job_id, INPUT_NAME)
            info = await to_thread(self._engine.inspect, source)
            if info.page_count > TELEGRAM_MAX_RENDERED_PDF_PAGES:
                raise PdfEngineError(
                    PdfErrorCode.PAGE_LIMIT_EXCEEDED,
                    "Telegram PDF rendering is limited to 20 pages per operation",
                )
            output_dir = workspace / "pages"
            rendered = await to_thread(self._engine.render_pages, source, output_dir)
            await self._storage.enforce_quota(job.job_id)
            refs = tuple(str(path) for path in rendered.output_paths)
            if not refs:
                raise UserFacingError(UserErrorCode.INTERNAL_ERROR.value)
        except Exception as exc:
            _emit_failure(job, started, exc)
            raise

        _emit(job, OperationStage.WORKER, OperationOutcome.SUCCESS, started)
        return ExecutionResult(
            output_ref=refs[0],
            additional_output_refs=refs[1:],
        )


class TelegramMediaExecutor(OperationExecutor):
    def __init__(self, storage: LocalTemporaryStorage, engine: MediaEngine | None = None) -> None:
        self._storage = storage
        self._engine = engine

    async def execute(
        self,
        job: JobSnapshot,
        operation: OperationDefinition,
        workspace: Path,
    ) -> ExecutionResult:
        del workspace
        started = monotonic()
        if operation.worker_family != "media":
            raise UserFacingError(UserErrorCode.INTERNAL_ERROR.value)

        try:
            engine = self._engine or MediaEngine()
            source = await self._storage.workspace_file(job.job_id, INPUT_NAME)
            destination = await self._media_destination(job, operation.operation_id)
            await _execute_media(engine, source, destination, operation.operation_id)
            await self._storage.enforce_quota(job.job_id)
        except Exception as exc:
            _emit_failure(job, started, exc)
            raise

        _emit(job, OperationStage.WORKER, OperationOutcome.SUCCESS, started)
        return ExecutionResult(output_ref=str(destination))

    async def _media_destination(self, job: JobSnapshot, operation_id: str) -> Path:
        suffix = {
            "audio.to_mp3": "mp3",
            "audio.to_m4a": "m4a",
            "audio.to_wav": "wav",
            "video.to_mp3": "mp3",
            "video.mute": "mp4",
            "video.to_gif": "gif",
            "video.compress": "mp4",
        }.get(operation_id)
        if suffix is None:
            raise UserFacingError(UserErrorCode.INTERNAL_ERROR.value)
        return await self._storage.workspace_file(job.job_id, f"result.{suffix}")


class TelegramOperationExecutor(OperationExecutor):
    def __init__(
        self,
        storage: LocalTemporaryStorage,
        *,
        image: TelegramImageExecutor | None = None,
        pdf: TelegramPdfExecutor | None = None,
        media: TelegramMediaExecutor | None = None,
    ) -> None:
        self._executors: dict[str, OperationExecutor] = {
            "image": image or TelegramImageExecutor(storage),
            "pdf": pdf or TelegramPdfExecutor(storage),
            "media": media or TelegramMediaExecutor(storage),
        }

    async def execute(
        self,
        job: JobSnapshot,
        operation: OperationDefinition,
        workspace: Path,
    ) -> ExecutionResult:
        executor = self._executors.get(operation.worker_family)
        if executor is None:
            raise UserFacingError(UserErrorCode.INTERNAL_ERROR.value)
        return await executor.execute(job, operation, workspace)


class TelegramDelivery(DeliveryPort):
    def __init__(self, bot: Bot) -> None:
        self._bot = bot

    async def deliver(self, job: JobSnapshot, result: ExecutionResult) -> None:
        started = monotonic()
        try:
            for index, output_ref in enumerate(result.output_refs):
                await self._bot.send_document(
                    job.chat_id,
                    FSInputFile(output_ref),
                    caption=operation_title(job.operation_id, Locale.RU) if index == 0 else None,
                )
        except Exception as exc:
            _emit(
                job,
                OperationStage.UPLOAD,
                OperationOutcome.FAILURE,
                started,
                error_code=UserErrorCode.TELEGRAM_UPLOAD_FAILED.value,
            )
            raise UserFacingError(UserErrorCode.TELEGRAM_UPLOAD_FAILED.value) from exc
        _emit(job, OperationStage.UPLOAD, OperationOutcome.SUCCESS, started)

    async def deliver_failure(self, job: JobSnapshot, error_code: str) -> None:
        try:
            await self._bot.send_message(
                job.chat_id,
                error_text(error_code, Locale.RU),
            )
        except Exception:
            LOGGER.exception("telegram failure notification failed")


class TelegramExecutionGateway:
    def __init__(
        self,
        *,
        bot: Bot,
        jobs: JobService,
        storage: LocalTemporaryStorage,
        rate_limiter: RedisUpdateRateLimiter,
    ) -> None:
        self._bot = bot
        self._jobs = jobs
        self._storage = storage
        self._rate_limiter = rate_limiter

    async def start_image(self, message: Message, operation_id: str) -> None:
        await self.start_operation(message, operation_id)

    async def start_operation(self, message: Message, operation_id: str) -> None:
        user = message.from_user
        attachment = message_file(message)
        if user is None or attachment is None:
            await message.answer(error_text(UserErrorCode.INTERNAL_ERROR.value, Locale.RU))
            return
        if not await self._rate_limiter.allow(user.id):
            await message.answer(error_text(UserErrorCode.RATE_LIMIT_EXCEEDED.value, Locale.RU))
            return

        request = StartJobRequest(
            user_id=user.id,
            chat_id=message.chat.id,
            source_message_id=message.message_id,
            operation_id=operation_id,
            operation_version=1,
        )
        try:
            result = await self._jobs.start_operation(
                request,
                prepare=lambda job: self._download(job, attachment),
            )
        except JobAdmissionRejected as exc:
            await message.answer(error_text(exc.code.value, Locale.RU))
            return
        except UserFacingError as exc:
            await message.answer(error_text(exc.code, Locale.RU))
            return
        except Exception:
            LOGGER.exception("telegram operation preparation failed")
            await message.answer(error_text(UserErrorCode.INTERNAL_ERROR.value, Locale.RU))
            return

        if result.created:
            await message.answer("Принято. Начинаю обработку файла.")
        else:
            await message.answer("Эта операция уже принята к обработке.")

    async def _download(self, job: JobSnapshot, attachment: TelegramFile) -> None:
        started = monotonic()
        try:
            if attachment.file_size is not None:
                await self._storage.enforce_quota(job.job_id, additional_bytes=attachment.file_size)
            destination = await self._storage.workspace_file(job.job_id, INPUT_NAME)
            remote = await self._bot.get_file(attachment.file_id)
            await self._bot.download(remote, destination=destination)
            await self._storage.enforce_quota(job.job_id)
        except Exception as exc:
            await self._storage.cleanup_workspace(job.job_id)
            raise UserFacingError(UserErrorCode.TELEGRAM_DOWNLOAD_FAILED.value) from exc
        _emit(job, OperationStage.VALIDATION, OperationOutcome.SUCCESS, started)


async def _execute_media(
    engine: MediaEngine,
    source: Path,
    destination: Path,
    operation_id: str,
) -> None:
    if operation_id == "audio.to_mp3":
        await to_thread(engine.convert_audio, source, destination, AudioOutputFormat.MP3)
        return
    if operation_id == "audio.to_m4a":
        await to_thread(engine.convert_audio, source, destination, AudioOutputFormat.M4A)
        return
    if operation_id == "audio.to_wav":
        await to_thread(engine.convert_audio, source, destination, AudioOutputFormat.WAV)
        return
    if operation_id == "video.to_mp3":
        await to_thread(engine.video_to_mp3, source, destination)
        return
    if operation_id == "video.mute":
        await to_thread(engine.mute_video, source, destination)
        return
    if operation_id == "video.to_gif":
        await to_thread(engine.video_to_gif, source, destination)
        return
    if operation_id == "video.compress":
        await to_thread(
            engine.compress_video,
            source,
            destination,
            VideoCompressionPreset.BALANCED,
        )
        return
    raise UserFacingError(UserErrorCode.INTERNAL_ERROR.value)


def _image_request(operation_id: str) -> tuple[ImageOutputFormat, CompressionPreset]:
    if operation_id == "image.to_jpeg":
        return ImageOutputFormat.JPEG, CompressionPreset.BALANCED
    if operation_id == "image.to_png":
        return ImageOutputFormat.PNG, CompressionPreset.BALANCED
    if operation_id == "image.to_webp":
        return ImageOutputFormat.WEBP, CompressionPreset.BALANCED
    if operation_id == "image.compress":
        return ImageOutputFormat.WEBP, CompressionPreset.SMALLEST
    raise UserFacingError(UserErrorCode.INTERNAL_ERROR.value)


def _emit_failure(job: JobSnapshot, started: float, exc: Exception) -> None:
    _emit(
        job,
        OperationStage.WORKER,
        OperationOutcome.FAILURE,
        started,
        error_code=_error_code(exc),
    )


def _emit(
    job: JobSnapshot,
    stage: OperationStage,
    outcome: OperationOutcome,
    started: float,
    *,
    error_code: str | None = None,
) -> None:
    emit_telemetry(
        LOGGER,
        TelemetryEvent.now(
            TelemetryEventType.OPERATION_STAGE,
            operation_id=job.operation_id,
            stage=stage,
            outcome=outcome,
            duration_ms=(monotonic() - started) * 1000,
            error_code=error_code,
            correlation_id=opaque_correlation_id(job.job_id),
        ),
    )


def _error_code(exc: Exception) -> str:
    code = getattr(exc, "code", UserErrorCode.INTERNAL_ERROR.value)
    return code.value if hasattr(code, "value") else str(code)
