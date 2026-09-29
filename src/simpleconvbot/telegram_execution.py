from __future__ import annotations

import logging
import re
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
from simpleconvbot.localization import (
    Locale,
    UserErrorCode,
    error_text,
    operation_title,
    resolve_locale,
)
from simpleconvbot.media_engine import (
    AudioOutputFormat,
    MediaEngine,
    VideoCompressionPreset,
)
from simpleconvbot.operations import OperationDefinition
from simpleconvbot.pdf_engine import (
    PageRange,
    PageSelection,
    PdfEngine,
    PdfEngineError,
    PdfErrorCode,
)
from simpleconvbot.ports import (
    DeliveryPort,
    ExecutionResult,
    LocalizedDeliveryText,
    OperationExecutor,
)
from simpleconvbot.redis_locale import RedisUserLocaleStore
from simpleconvbot.redis_security import RedisUpdateRateLimiter
from simpleconvbot.services import JobService, StartJobRequest
from simpleconvbot.storage import (
    LocalTemporaryStorage,
    StorageErrorCode,
    StorageSecurityError,
)
from simpleconvbot.telemetry import (
    OperationMetricRecorder,
    OperationOutcome,
    OperationStage,
    TelemetryEvent,
    TelemetryEventType,
    emit_operation_telemetry,
    opaque_correlation_id,
)
from simpleconvbot.ui import (
    operation_accepted_text,
    operation_duplicate_text,
    pdf_info_text,
)

LOGGER = logging.getLogger(__name__)
INPUT_NAME = "input"
TELEGRAM_MAX_RENDERED_PDF_PAGES = 20
TELEGRAM_MAX_SPLIT_PDF_PAGES = 20
TELEGRAM_MAX_COLLECTION_FILES = 20
_COLLECTION_INPUT = re.compile(r"^input-(?P<position>[0-9]{4})$")


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
    if callback_data is None:
        return None
    return {
        "ui:pdf:jpg": "pdf.to_jpeg_images",
        "ui:pdf:png": "pdf.to_images",
        "ui:pdf:split": "pdf.extract_pages",
        "ui:pdf:info": "pdf.info",
    }.get(callback_data)


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
    def __init__(
        self,
        storage: LocalTemporaryStorage,
        engine: ImageEngine | None = None,
        *,
        metrics: OperationMetricRecorder | None = None,
    ) -> None:
        self._storage = storage
        self._engine = engine or ImageEngine()
        self._metrics = metrics

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
            _emit_failure(job, started, exc, self._metrics)
            raise
        _emit(job, OperationStage.WORKER, OperationOutcome.SUCCESS, started, metrics=self._metrics)
        return ExecutionResult(output_ref=str(destination))


class TelegramPdfExecutor(OperationExecutor):
    def __init__(
        self,
        storage: LocalTemporaryStorage,
        engine: PdfEngine | None = None,
        *,
        metrics: OperationMetricRecorder | None = None,
    ) -> None:
        self._storage = storage
        self._engine = engine or PdfEngine()
        self._metrics = metrics

    async def execute(
        self,
        job: JobSnapshot,
        operation: OperationDefinition,
        workspace: Path,
    ) -> ExecutionResult:
        started = monotonic()
        if operation.worker_family != "pdf":
            raise UserFacingError(UserErrorCode.INTERNAL_ERROR.value)

        try:
            if operation.operation_id == "pdf.to_images":
                result = await self._render_single_pdf(
                    job,
                    workspace,
                    output_format=ImageOutputFormat.PNG,
                )
            elif operation.operation_id == "pdf.to_jpeg_images":
                result = await self._render_single_pdf(
                    job,
                    workspace,
                    output_format=ImageOutputFormat.JPEG,
                )
            elif operation.operation_id == "pdf.from_images":
                result = await self._images_to_pdf(job, workspace)
            elif operation.operation_id == "pdf.merge":
                result = await self._merge_pdfs(job, workspace)
            elif operation.operation_id == "pdf.extract_pages":
                result = await self._split_pdf(job)
            elif operation.operation_id == "pdf.info":
                result = await self._inspect_pdf(job)
            else:
                raise UserFacingError(UserErrorCode.INTERNAL_ERROR.value)
            await self._storage.enforce_quota(job.job_id)
        except Exception as exc:
            _emit_failure(job, started, exc, self._metrics)
            raise

        _emit(job, OperationStage.WORKER, OperationOutcome.SUCCESS, started, metrics=self._metrics)
        return result

    async def _render_single_pdf(
        self,
        job: JobSnapshot,
        workspace: Path,
        *,
        output_format: ImageOutputFormat,
    ) -> ExecutionResult:
        source = await self._storage.workspace_file(job.job_id, INPUT_NAME)
        info = await to_thread(self._engine.inspect, source)
        if info.page_count > TELEGRAM_MAX_RENDERED_PDF_PAGES:
            raise PdfEngineError(
                PdfErrorCode.PAGE_LIMIT_EXCEEDED,
                "Telegram PDF rendering exceeds the page fan-out limit",
            )
        output_dir = workspace / "pages"
        rendered = await to_thread(
            self._engine.render_pages,
            source,
            output_dir,
            output_format=output_format,
        )
        refs = tuple(str(path) for path in rendered.output_paths)
        if not refs:
            raise UserFacingError(UserErrorCode.INTERNAL_ERROR.value)
        return ExecutionResult(
            output_ref=refs[0],
            additional_output_refs=refs[1:],
        )

    async def _inspect_pdf(self, job: JobSnapshot) -> ExecutionResult:
        source = await self._storage.workspace_file(job.job_id, INPUT_NAME)
        info = await to_thread(self._engine.inspect, source)
        return ExecutionResult(
            delivery_text=LocalizedDeliveryText(
                ru=pdf_info_text(
                    info.page_count,
                    info.byte_size,
                    info.version,
                    Locale.RU,
                ),
                en=pdf_info_text(
                    info.page_count,
                    info.byte_size,
                    info.version,
                    Locale.EN,
                ),
            )
        )

    async def _split_pdf(self, job: JobSnapshot) -> ExecutionResult:
        source = await self._storage.workspace_file(job.job_id, INPUT_NAME)
        info = await to_thread(self._engine.inspect, source)
        if info.page_count > TELEGRAM_MAX_SPLIT_PDF_PAGES:
            raise PdfEngineError(
                PdfErrorCode.PAGE_LIMIT_EXCEEDED,
                "Telegram PDF split exceeds the document fan-out limit",
            )

        refs: list[str] = []
        for page_number in range(1, info.page_count + 1):
            destination = await self._storage.workspace_file(
                job.job_id,
                f"page-{page_number:04d}.pdf",
            )
            await to_thread(
                self._engine.extract_pages,
                source,
                destination,
                PageSelection((PageRange(page_number, page_number),)),
            )
            refs.append(str(destination))

        if not refs:
            raise UserFacingError(UserErrorCode.INTERNAL_ERROR.value)
        return ExecutionResult(output_ref=refs[0], additional_output_refs=tuple(refs[1:]))

    async def _images_to_pdf(
        self,
        job: JobSnapshot,
        workspace: Path,
    ) -> ExecutionResult:
        inputs = _ordered_collection_inputs(workspace)
        destination = await self._storage.workspace_file(job.job_id, "result.pdf")
        await to_thread(self._engine.images_to_pdf, inputs, destination)
        return ExecutionResult(output_ref=str(destination))

    async def _merge_pdfs(
        self,
        job: JobSnapshot,
        workspace: Path,
    ) -> ExecutionResult:
        inputs = _ordered_collection_inputs(workspace)
        destination = await self._storage.workspace_file(job.job_id, "result.pdf")
        await to_thread(self._engine.merge, inputs, destination)
        return ExecutionResult(output_ref=str(destination))


class TelegramMediaExecutor(OperationExecutor):
    def __init__(
        self,
        storage: LocalTemporaryStorage,
        engine: MediaEngine | None = None,
        *,
        metrics: OperationMetricRecorder | None = None,
    ) -> None:
        self._storage = storage
        self._engine = engine
        self._metrics = metrics

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
            _emit_failure(job, started, exc, self._metrics)
            raise

        _emit(job, OperationStage.WORKER, OperationOutcome.SUCCESS, started, metrics=self._metrics)
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
        metrics: OperationMetricRecorder | None = None,
    ) -> None:
        self._executors: dict[str, OperationExecutor] = {
            "image": image or TelegramImageExecutor(storage, metrics=metrics),
            "pdf": pdf or TelegramPdfExecutor(storage, metrics=metrics),
            "media": media or TelegramMediaExecutor(storage, metrics=metrics),
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
    def __init__(
        self,
        bot: Bot,
        locale_store: RedisUserLocaleStore | None = None,
        metrics: OperationMetricRecorder | None = None,
    ) -> None:
        self._bot = bot
        self._locale_store = locale_store
        self._metrics = metrics

    async def deliver(self, job: JobSnapshot, result: ExecutionResult) -> None:
        started = monotonic()
        locale = await _stored_locale(self._locale_store, job.user_id)
        try:
            if result.delivery_text is not None:
                text = (
                    result.delivery_text.ru
                    if locale is Locale.RU
                    else result.delivery_text.en
                )
                await self._bot.send_message(job.chat_id, text)
            else:
                for index, output_ref in enumerate(result.output_refs):
                    await self._bot.send_document(
                        job.chat_id,
                        FSInputFile(output_ref),
                        caption=(operation_title(job.operation_id, locale) if index == 0 else None),
                    )
        except Exception as exc:
            _emit(
                job,
                OperationStage.UPLOAD,
                OperationOutcome.FAILURE,
                started,
                error_code=UserErrorCode.TELEGRAM_UPLOAD_FAILED.value,
                metrics=self._metrics,
            )
            raise UserFacingError(UserErrorCode.TELEGRAM_UPLOAD_FAILED.value) from exc
        _emit(
            job,
            OperationStage.UPLOAD,
            OperationOutcome.SUCCESS,
            started,
            metrics=self._metrics,
        )

    async def deliver_failure(self, job: JobSnapshot, error_code: str) -> None:
        locale = await _stored_locale(self._locale_store, job.user_id)
        try:
            await self._bot.send_message(
                job.chat_id,
                error_text(error_code, locale),
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
        locale_store: RedisUserLocaleStore | None = None,
        metrics: OperationMetricRecorder | None = None,
    ) -> None:
        self._bot = bot
        self._jobs = jobs
        self._storage = storage
        self._rate_limiter = rate_limiter
        self._locale_store = locale_store
        self._metrics = metrics

    async def start_image(
        self,
        message: Message,
        operation_id: str,
        *,
        locale: Locale | None = None,
    ) -> None:
        await self.start_operation(message, operation_id, locale=locale)

    async def start_operation(
        self,
        message: Message,
        operation_id: str,
        *,
        locale: Locale | None = None,
    ) -> None:
        user = message.from_user
        attachment = message_file(message)
        current_locale = locale or resolve_locale(user.language_code if user is not None else None)
        if user is None or attachment is None:
            await message.answer(error_text(UserErrorCode.INTERNAL_ERROR.value, current_locale))
            return

        await _remember_locale(self._locale_store, user.id, current_locale)
        if not await self._rate_limiter.allow(user.id):
            await message.answer(
                error_text(UserErrorCode.RATE_LIMIT_EXCEEDED.value, current_locale)
            )
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
            await message.answer(error_text(exc.code.value, current_locale))
            return
        except UserFacingError as exc:
            await message.answer(error_text(exc.code, current_locale))
            return
        except Exception:
            LOGGER.exception("telegram operation preparation failed")
            await message.answer(error_text(UserErrorCode.INTERNAL_ERROR.value, current_locale))
            return

        if result.created:
            await message.answer(operation_accepted_text(current_locale))
        else:
            await message.answer(operation_duplicate_text(current_locale))

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
            code = telegram_download_error_code(exc)
            await self._storage.cleanup_workspace(job.job_id)
            _emit(
                job,
                OperationStage.VALIDATION,
                OperationOutcome.FAILURE,
                started,
                error_code=code,
                metrics=self._metrics,
            )
            raise UserFacingError(code) from exc
        _emit(
            job,
            OperationStage.VALIDATION,
            OperationOutcome.SUCCESS,
            started,
            metrics=self._metrics,
        )


def telegram_download_error_code(exc: Exception) -> str:
    if isinstance(exc, UserFacingError):
        return exc.code
    if isinstance(exc, StorageSecurityError):
        if exc.code is StorageErrorCode.QUOTA_EXCEEDED:
            return UserErrorCode.TELEGRAM_INPUT_TOO_LARGE.value
        return exc.code.value
    return UserErrorCode.TELEGRAM_DOWNLOAD_FAILED.value


async def _remember_locale(
    store: RedisUserLocaleStore | None,
    user_id: int,
    locale: Locale,
) -> None:
    if store is None:
        return
    try:
        await store.remember(user_id, locale)
    except Exception:
        LOGGER.exception("telegram locale hint write failed")


async def _stored_locale(
    store: RedisUserLocaleStore | None,
    user_id: int,
) -> Locale:
    if store is None:
        return Locale.RU
    try:
        return await store.get(user_id) or Locale.RU
    except Exception:
        LOGGER.exception("telegram locale hint read failed")
        return Locale.RU


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


def _emit_failure(
    job: JobSnapshot,
    started: float,
    exc: Exception,
    metrics: OperationMetricRecorder | None = None,
) -> None:
    _emit(
        job,
        OperationStage.WORKER,
        OperationOutcome.FAILURE,
        started,
        error_code=_error_code(exc),
        metrics=metrics,
    )


def _emit(
    job: JobSnapshot,
    stage: OperationStage,
    outcome: OperationOutcome,
    started: float,
    *,
    error_code: str | None = None,
    metrics: OperationMetricRecorder | None = None,
) -> None:
    emit_operation_telemetry(
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
        metrics,
    )


def _error_code(exc: Exception) -> str:
    code = getattr(exc, "code", UserErrorCode.INTERNAL_ERROR.value)
    return code.value if hasattr(code, "value") else str(code)


def _ordered_collection_inputs(workspace: Path) -> tuple[Path, ...]:
    indexed: list[tuple[int, Path]] = []
    for path in workspace.iterdir():
        match = _COLLECTION_INPUT.fullmatch(path.name)
        if match is None:
            continue
        if path.is_symlink() or not path.is_file():
            raise UserFacingError(UserErrorCode.INTERNAL_ERROR.value)
        indexed.append((int(match.group("position")), path))

    indexed.sort(key=lambda item: item[0])
    if not indexed or len(indexed) > TELEGRAM_MAX_COLLECTION_FILES:
        raise UserFacingError(UserErrorCode.INTERNAL_ERROR.value)

    expected = list(range(1, len(indexed) + 1))
    actual = [position for position, _ in indexed]
    if actual != expected:
        raise UserFacingError(UserErrorCode.INTERNAL_ERROR.value)
    return tuple(path for _, path in indexed)
