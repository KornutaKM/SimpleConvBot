from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from time import monotonic
from uuid import UUID

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.types import CallbackQuery, Message

from simpleconvbot.jobs import JobAdmissionRejected, JobSnapshot, JobState
from simpleconvbot.localization import (
    Locale,
    UserErrorCode,
    error_text,
    operation_title,
    resolve_locale,
)
from simpleconvbot.postgres import PostgresCollectionSessionRepository
from simpleconvbot.redis_locale import RedisUserLocaleStore
from simpleconvbot.redis_security import RedisUpdateRateLimiter
from simpleconvbot.redis_sessions import RedisSessionFocusStore
from simpleconvbot.services import JobService, StartJobRequest
from simpleconvbot.sessions import (
    CollectionSessionSnapshot,
    FinalizedSessionPlan,
    SessionAccessDenied,
    SessionClosed,
    SessionEmpty,
    SessionExpired,
    SessionFileInput,
    SessionIdempotencyConflict,
    SessionKind,
    SessionLimitExceeded,
    SessionNotFound,
    SessionPolicy,
    SessionState,
)
from simpleconvbot.storage import LocalTemporaryStorage
from simpleconvbot.telegram_execution import TelegramFile, UserFacingError, message_file
from simpleconvbot.telemetry import (
    OperationOutcome,
    OperationStage,
    TelemetryEvent,
    TelemetryEventType,
    emit_telemetry,
    opaque_correlation_id,
)
from simpleconvbot.ui import (
    collection_accepted_text,
    collection_duplicate_text,
    collection_keyboard,
    collection_status_text,
    session_add_hint,
    session_cancelled_text,
    session_unavailable_text,
)

LOGGER = logging.getLogger(__name__)
_SESSION_CALLBACK = re.compile(
    r"^sess:(?P<action>add|done|cancel):"
    r"(?P<session>[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12})$"
)


class TelegramCollectionGateway:
    def __init__(
        self,
        *,
        bot: Bot,
        repository: PostgresCollectionSessionRepository,
        focus: RedisSessionFocusStore,
        jobs: JobService,
        storage: LocalTemporaryStorage,
        rate_limiter: RedisUpdateRateLimiter,
        locale_store: RedisUserLocaleStore | None = None,
        policy: SessionPolicy | None = None,
    ) -> None:
        self._bot = bot
        self._repository = repository
        self._focus = focus
        self._jobs = jobs
        self._storage = storage
        self._rate_limiter = rate_limiter
        self._locale_store = locale_store
        self._policy = policy or SessionPolicy()

    async def start(
        self,
        message: Message,
        kind: SessionKind,
        *,
        locale: Locale | None = None,
    ) -> None:
        user = message.from_user
        current_locale = locale or resolve_locale(
            user.language_code if user is not None else None
        )
        if user is None:
            await message.answer(
                error_text(UserErrorCode.INTERNAL_ERROR.value, current_locale)
            )
            return
        await _remember_locale(self._locale_store, user.id, current_locale)
        if not await self._rate_limiter.allow(user.id):
            await message.answer(error_text(UserErrorCode.RATE_LIMIT_EXCEEDED.value, current_locale))
            return
        if not _message_matches_kind(message, kind):
            await message.answer(error_text(UserErrorCode.SESSION_WRONG_FILE_TYPE.value, current_locale))
            return

        active = await self._focus.get(user_id=user.id, chat_id=message.chat.id)
        if active is not None:
            try:
                snapshot = await self._repository.get_owned(
                    active,
                    owner_user_id=user.id,
                    chat_id=message.chat.id,
                )
            except (SessionNotFound, SessionAccessDenied):
                await self._focus.clear(
                    user_id=user.id,
                    chat_id=message.chat.id,
                    expected_session_id=active,
                )
            else:
                if (
                    snapshot.state is SessionState.COLLECTING
                    and datetime.now(UTC) < snapshot.expires_at
                ):
                    await message.answer(
                        error_text(UserErrorCode.SESSION_ALREADY_ACTIVE.value, current_locale),
                        reply_markup=collection_keyboard(snapshot.session_id, current_locale),
                    )
                    return
                await self._focus.clear(
                    user_id=user.id,
                    chat_id=message.chat.id,
                    expected_session_id=active,
                )

        attachment = message_file(message)
        if attachment is None:
            await message.answer(error_text(UserErrorCode.INTERNAL_ERROR.value, current_locale))
            return

        created_session_id: UUID | None = None
        try:
            byte_size = await self._resolved_size(attachment)
            created = await self._repository.create(
                kind=kind,
                owner_user_id=user.id,
                chat_id=message.chat.id,
            )
            created_session_id = created.session_id
            snapshot, _ = await self._repository.add_file(
                created.session_id,
                owner_user_id=user.id,
                chat_id=message.chat.id,
                item=SessionFileInput(
                    source_message_id=message.message_id,
                    object_ref=attachment.file_id,
                    byte_size=byte_size,
                ),
            )
            await self._focus.set(
                user_id=user.id,
                chat_id=message.chat.id,
                session_id=snapshot.session_id,
                ttl_seconds=_remaining_ttl(snapshot),
            )
        except Exception as exc:
            if created_session_id is not None:
                await self._cancel_collecting_best_effort(
                    created_session_id,
                    user_id=user.id,
                    chat_id=message.chat.id,
                )
            await message.answer(error_text(_session_error_code(exc), current_locale))
            return

        await message.answer(
            collection_status_text(snapshot, current_locale),
            reply_markup=collection_keyboard(snapshot.session_id, current_locale),
            parse_mode=ParseMode.HTML,
        )

    async def consume(self, message: Message) -> bool:
        user = message.from_user
        if user is None:
            return False
        current_locale = resolve_locale(user.language_code)
        await _remember_locale(self._locale_store, user.id, current_locale)

        session_id = await self._focus.get(user_id=user.id, chat_id=message.chat.id)
        if session_id is None:
            return False

        try:
            snapshot = await self._repository.get_owned(
                session_id,
                owner_user_id=user.id,
                chat_id=message.chat.id,
            )
        except Exception as exc:
            await self._focus.clear(
                user_id=user.id,
                chat_id=message.chat.id,
                expected_session_id=session_id,
            )
            await message.answer(error_text(_session_error_code(exc), current_locale))
            return True

        if (
            snapshot.state is not SessionState.COLLECTING
            or datetime.now(UTC) >= snapshot.expires_at
        ):
            await self._focus.clear(
                user_id=user.id,
                chat_id=message.chat.id,
                expected_session_id=session_id,
            )
            code = (
                UserErrorCode.SESSION_EXPIRED.value
                if datetime.now(UTC) >= snapshot.expires_at
                else UserErrorCode.SESSION_CLOSED.value
            )
            await message.answer(error_text(code, current_locale))
            return True

        if not await self._rate_limiter.allow(user.id):
            await message.answer(error_text(UserErrorCode.RATE_LIMIT_EXCEEDED.value, current_locale))
            return True
        if not _message_matches_kind(message, snapshot.kind):
            await message.answer(error_text(UserErrorCode.SESSION_WRONG_FILE_TYPE.value, current_locale))
            return True

        attachment = message_file(message)
        if attachment is None:
            await message.answer(error_text(UserErrorCode.INTERNAL_ERROR.value, current_locale))
            return True

        try:
            byte_size = await self._resolved_size(attachment)
            updated, _ = await self._repository.add_file(
                session_id,
                owner_user_id=user.id,
                chat_id=message.chat.id,
                item=SessionFileInput(
                    source_message_id=message.message_id,
                    object_ref=attachment.file_id,
                    byte_size=byte_size,
                ),
            )
            await self._focus.set(
                user_id=user.id,
                chat_id=message.chat.id,
                session_id=session_id,
                ttl_seconds=_remaining_ttl(updated),
            )
        except Exception as exc:
            if isinstance(exc, SessionExpired | SessionClosed | SessionNotFound):
                await self._focus.clear(
                    user_id=user.id,
                    chat_id=message.chat.id,
                    expected_session_id=session_id,
                )
            await message.answer(error_text(_session_error_code(exc), current_locale))
            return True

        await message.answer(
            collection_status_text(updated, current_locale),
            reply_markup=collection_keyboard(updated.session_id, current_locale),
            parse_mode=ParseMode.HTML,
        )
        return True

    async def handle_callback(self, callback: CallbackQuery) -> None:
        parsed = parse_session_callback(callback.data)
        message = callback.message
        user = callback.from_user
        current_locale = resolve_locale(user.language_code)
        await _remember_locale(self._locale_store, user.id, current_locale)
        if parsed is None or not isinstance(message, Message):
            await callback.answer(session_unavailable_text(current_locale), show_alert=True)
            return

        action, session_id = parsed
        if not await self._rate_limiter.allow(user.id):
            await callback.answer(
                error_text(UserErrorCode.RATE_LIMIT_EXCEEDED.value, current_locale),
                show_alert=True,
            )
            return

        try:
            if action == "add":
                snapshot = await self._repository.get_owned(
                    session_id,
                    owner_user_id=user.id,
                    chat_id=message.chat.id,
                )
                if snapshot.state is not SessionState.COLLECTING:
                    raise SessionClosed("session is finalized")
                ttl = _remaining_ttl(snapshot)
                await self._focus.set(
                    user_id=user.id,
                    chat_id=message.chat.id,
                    session_id=session_id,
                    ttl_seconds=ttl,
                )
                await callback.answer(session_add_hint(current_locale), show_alert=True)
                return

            if action == "cancel":
                await self._repository.cancel(
                    session_id,
                    owner_user_id=user.id,
                    chat_id=message.chat.id,
                )
                await self._focus.clear(
                    user_id=user.id,
                    chat_id=message.chat.id,
                    expected_session_id=session_id,
                )
                await message.edit_text(session_cancelled_text(current_locale))
                await callback.answer()
                return

            plan = await self._repository.finalize(
                session_id,
                owner_user_id=user.id,
                chat_id=message.chat.id,
            )
            await self._focus.clear(
                user_id=user.id,
                chat_id=message.chat.id,
                expected_session_id=session_id,
            )
            await callback.answer()
            await self._enqueue_finalized(message, user.id, plan, current_locale)
        except Exception as exc:
            await callback.answer(error_text(_session_error_code(exc), current_locale), show_alert=True)

    async def _enqueue_finalized(
        self,
        message: Message,
        user_id: int,
        plan: FinalizedSessionPlan,
        locale: Locale,
    ) -> None:
        request = StartJobRequest(
            user_id=user_id,
            chat_id=message.chat.id,
            source_message_id=plan.files[0].source_message_id,
            operation_id=plan.operation_id,
            operation_version=1,
            idempotency_token=str(plan.session_id),
        )
        try:
            result = await self._jobs.start_operation(
                request,
                prepare=lambda job: self._download_plan(job, plan),
            )
        except JobAdmissionRejected as exc:
            await message.answer(error_text(exc.code.value, locale))
            return
        except Exception as exc:
            await self._delete_finalized_best_effort(
                plan.session_id,
                user_id=user_id,
                chat_id=message.chat.id,
            )
            await message.answer(error_text(_session_error_code(exc), locale))
            return

        await self._delete_finalized_best_effort(
            plan.session_id,
            user_id=user_id,
            chat_id=message.chat.id,
        )
        if result.job.state is JobState.FAILED:
            await message.answer(error_text(UserErrorCode.INTERNAL_ERROR.value, locale))
            return
        if result.created:
            await message.answer(
                collection_accepted_text(operation_title(plan.operation_id, locale), locale)
            )
        else:
            await message.answer(collection_duplicate_text(locale))

    async def _download_plan(
        self,
        job: JobSnapshot,
        plan: FinalizedSessionPlan,
    ) -> None:
        started = monotonic()
        expected_total = sum(item.byte_size for item in plan.files)
        try:
            await self._storage.enforce_quota(job.job_id, additional_bytes=expected_total)
            for index, item in enumerate(plan.files, start=1):
                remote = await self._bot.get_file(item.object_ref)
                remote_size = remote.file_size
                if remote_size is not None and remote_size != item.byte_size:
                    raise UserFacingError(UserErrorCode.SESSION_IDEMPOTENCY_CONFLICT.value)
                destination = await self._storage.workspace_file(
                    job.job_id,
                    f"input-{index:04d}",
                )
                await self._bot.download(remote, destination=destination)
                await self._storage.enforce_quota(job.job_id)
        except Exception as exc:
            await self._storage.cleanup_workspace(job.job_id)
            _emit_download(job, started, OperationOutcome.FAILURE, _session_error_code(exc))
            if isinstance(exc, UserFacingError):
                raise
            raise UserFacingError(UserErrorCode.TELEGRAM_DOWNLOAD_FAILED.value) from exc
        _emit_download(job, started, OperationOutcome.SUCCESS)

    async def _resolved_size(self, attachment: TelegramFile) -> int:
        if attachment.file_size is not None and attachment.file_size > 0:
            return attachment.file_size
        remote = await self._bot.get_file(attachment.file_id)
        if remote.file_size is None or remote.file_size <= 0:
            raise UserFacingError(UserErrorCode.TELEGRAM_FILE_SIZE_UNKNOWN.value)
        return remote.file_size

    async def _cancel_collecting_best_effort(
        self,
        session_id: UUID,
        *,
        user_id: int,
        chat_id: int,
    ) -> None:
        try:
            await self._repository.cancel(
                session_id,
                owner_user_id=user_id,
                chat_id=chat_id,
            )
        except Exception:
            LOGGER.exception("abandoned collection session cleanup failed")

    async def _delete_finalized_best_effort(
        self,
        session_id: UUID,
        *,
        user_id: int,
        chat_id: int,
    ) -> None:
        try:
            await self._repository.delete_finalized(
                session_id,
                owner_user_id=user_id,
                chat_id=chat_id,
            )
        except Exception:
            LOGGER.exception("finalized collection session cleanup failed")


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
        LOGGER.exception("telegram session locale hint write failed")


def parse_session_callback(raw: str | None) -> tuple[str, UUID] | None:
    if raw is None:
        return None
    match = _SESSION_CALLBACK.fullmatch(raw)
    if match is None:
        return None
    return match.group("action"), UUID(match.group("session"))


def _message_matches_kind(message: Message, kind: SessionKind) -> bool:
    if kind is SessionKind.IMAGES_TO_PDF:
        if message.photo:
            return True
        document = message.document
        return bool(
            document is not None
            and document.mime_type is not None
            and document.mime_type.startswith("image/")
        )

    document = message.document
    return bool(document is not None and document.mime_type == "application/pdf")


def _remaining_ttl(snapshot: CollectionSessionSnapshot) -> int:
    remaining = int((snapshot.expires_at - datetime.now(UTC)).total_seconds())
    if remaining <= 0:
        raise SessionExpired("collection session has expired")
    return remaining


def _session_error_code(exc: Exception) -> str:
    if isinstance(exc, UserFacingError):
        return exc.code
    mapping: tuple[tuple[type[Exception], UserErrorCode], ...] = (
        (SessionNotFound, UserErrorCode.SESSION_NOT_FOUND),
        (SessionAccessDenied, UserErrorCode.SESSION_ACCESS_DENIED),
        (SessionExpired, UserErrorCode.SESSION_EXPIRED),
        (SessionClosed, UserErrorCode.SESSION_CLOSED),
        (SessionEmpty, UserErrorCode.SESSION_EMPTY),
        (SessionLimitExceeded, UserErrorCode.SESSION_LIMIT_EXCEEDED),
        (SessionIdempotencyConflict, UserErrorCode.SESSION_IDEMPOTENCY_CONFLICT),
    )
    for error_type, code in mapping:
        if isinstance(exc, error_type):
            return code.value
    return UserErrorCode.INTERNAL_ERROR.value


def _emit_download(
    job: JobSnapshot,
    started: float,
    outcome: OperationOutcome,
    error_code: str | None = None,
) -> None:
    emit_telemetry(
        LOGGER,
        TelemetryEvent.now(
            TelemetryEventType.OPERATION_STAGE,
            operation_id=job.operation_id,
            stage=OperationStage.VALIDATION,
            outcome=outcome,
            duration_ms=(monotonic() - started) * 1000,
            error_code=error_code,
            correlation_id=opaque_correlation_id(job.job_id),
        ),
    )
