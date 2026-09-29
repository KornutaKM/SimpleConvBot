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
from simpleconvbot.operations import OperationDefinition
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
            _emit(
                job,
                OperationStage.WORKER,
                OperationOutcome.FAILURE,
                started,
                error_code=_error_code(exc),
            )
            raise
        _emit(job, OperationStage.WORKER, OperationOutcome.SUCCESS, started)
        return ExecutionResult(output_ref=str(destination))


class TelegramDelivery(DeliveryPort):
    def __init__(self, bot: Bot) -> None:
        self._bot = bot

    async def deliver(self, job: JobSnapshot, result: ExecutionResult) -> None:
        started = monotonic()
        try:
            await self._bot.send_document(
                job.chat_id,
                FSInputFile(result.output_ref),
                caption=operation_title(job.operation_id, Locale.RU),
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
