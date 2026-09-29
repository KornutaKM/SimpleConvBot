from __future__ import annotations

import logging
from asyncio import Event, TaskGroup, create_task, wait_for
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from time import monotonic

from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine

from simpleconvbot.config import Settings, SettingsError
from simpleconvbot.diagnostics import AdminDiagnostics, emit_admin_diagnostics
from simpleconvbot.gateway import create_dispatcher
from simpleconvbot.health import HealthReport, collect_health
from simpleconvbot.image_operations import IMAGE_OPERATIONS
from simpleconvbot.jobs import JobAdmissionPolicy
from simpleconvbot.logging_security import configure_secure_logging
from simpleconvbot.maintenance import RetentionSweepResult, RetentionSweepService
from simpleconvbot.media_operations import MEDIA_OPERATIONS
from simpleconvbot.metrics import MetricsRegistry
from simpleconvbot.operations import OperationRegistry
from simpleconvbot.pdf_operations import PDF_OPERATIONS
from simpleconvbot.postgres import (
    PostgresCollectionSessionRepository,
    PostgresJobRepository,
    PostgresUpdateReceiptStore,
    create_schema,
    make_engine,
    make_session_factory,
)
from simpleconvbot.recovery import StartupRecoveryService
from simpleconvbot.redis_locale import RedisUserLocaleStore
from simpleconvbot.redis_queue import RedisJobQueue
from simpleconvbot.redis_security import RedisUpdateRateLimiter
from simpleconvbot.redis_sessions import RedisSessionFocusStore
from simpleconvbot.services import JobService, JobWorker, QueueWorker
from simpleconvbot.sessions import SessionPolicy
from simpleconvbot.storage import LocalTemporaryStorage
from simpleconvbot.telegram_execution import (
    TelegramDelivery,
    TelegramExecutionGateway,
    TelegramOperationExecutor,
)
from simpleconvbot.telegram_sessions import TelegramCollectionGateway
from simpleconvbot.telemetry import (
    OperationOutcome,
    TelemetryEvent,
    TelemetryEventType,
    emit_telemetry,
)

LOGGER = logging.getLogger(__name__)


async def run_polling(settings: Settings | None = None) -> None:
    current = settings or Settings.from_env()
    current.validate_runtime()
    token = current.telegram_bot_token
    if token is None:
        raise SettingsError("TELEGRAM_BOT_TOKEN is required for bot runtime")

    configure_secure_logging(
        current.log_level,
        sensitive_values=(
            token,
            current.database_url,
            current.redis_url,
        ),
    )
    runtime_started = monotonic()
    runtime_version = _package_version()
    engine = make_engine(current.database_url)
    sessions = make_session_factory(engine)
    redis_client = Redis.from_url(current.redis_url, decode_responses=True)
    bot = Bot(token=token)
    storage = LocalTemporaryStorage(
        current.temp_root,
        max_workspace_bytes=current.workspace_max_bytes,
    )
    registry = OperationRegistry((*IMAGE_OPERATIONS, *PDF_OPERATIONS, *MEDIA_OPERATIONS))
    queue = RedisJobQueue(redis_client)
    metrics = MetricsRegistry()
    repository = PostgresJobRepository(
        sessions,
        JobAdmissionPolicy(
            max_active_per_user=current.max_active_jobs_per_user,
            max_active_global=current.max_active_jobs_global,
        ),
    )
    jobs = JobService(repository, queue, registry, metrics=metrics)
    rate_limiter = RedisUpdateRateLimiter(
        redis_client,
        limit=current.update_rate_limit_per_minute,
    )
    locale_store = RedisUserLocaleStore(redis_client)
    execution = TelegramExecutionGateway(
        bot=bot,
        jobs=jobs,
        storage=storage,
        rate_limiter=rate_limiter,
        locale_store=locale_store,
        metrics=metrics,
    )
    session_policy = SessionPolicy()
    session_repository = PostgresCollectionSessionRepository(sessions, session_policy)
    collections = TelegramCollectionGateway(
        bot=bot,
        repository=session_repository,
        focus=RedisSessionFocusStore(redis_client),
        jobs=jobs,
        storage=storage,
        rate_limiter=rate_limiter,
        locale_store=locale_store,
        metrics=metrics,
        policy=session_policy,
    )
    dispatcher = create_dispatcher(
        PostgresUpdateReceiptStore(sessions),
        execution,
        collections,
    )
    delivery = TelegramDelivery(bot, locale_store, metrics)
    recovery = StartupRecoveryService(
        repository=repository,
        queue=queue,
        storage=storage,
        failure_delivery=delivery,
    )
    retention = RetentionSweepService(
        workspace_reaper=storage,
        session_reaper=session_repository,
        metrics=metrics,
        workspace_ttl_seconds=current.temp_ttl_seconds,
    )
    worker = QueueWorker(
        queue,
        JobWorker(
            repository,
            registry,
            storage,
            TelegramOperationExecutor(storage, metrics=metrics),
            delivery,
            failure_delivery=delivery,
            metrics=metrics,
        ),
    )
    stop_runtime = Event()

    try:
        await create_schema(engine)
        await redis_client.ping()
        await recovery.recover()
        _emit_retention_policy(
            ttl_seconds=current.temp_ttl_seconds,
            interval_seconds=current.retention_sweep_interval_seconds,
        )
        initial_retention = await retention.sweep()
        _require_complete_initial_retention(initial_retention)
        initial_health = await collect_health(engine, redis_client)
        _emit_diagnostics_snapshot(
            initial_health,
            metrics,
            version_name=runtime_version,
            environment=current.environment.value,
            runtime_started=runtime_started,
        )
        _require_ready_health(initial_health)
        await bot.set_my_commands(
            [
                BotCommand(command="start", description="Home"),
                BotCommand(command="tools", description="All tools"),
                BotCommand(command="settings", description="Settings"),
            ]
        )
        await bot.set_my_commands(
            [
                BotCommand(command="start", description="Главный экран"),
                BotCommand(command="tools", description="Все инструменты"),
                BotCommand(command="settings", description="Настройки"),
            ],
            language_code="ru",
        )
        retention_task = create_task(
            _run_retention(
                retention,
                stop_runtime,
                interval_seconds=current.retention_sweep_interval_seconds,
            )
        )
        diagnostics_task = create_task(
            _run_diagnostics(
                engine,
                redis_client,
                metrics,
                stop_runtime,
                version_name=runtime_version,
                environment=current.environment.value,
                runtime_started=runtime_started,
                interval_seconds=current.diagnostics_interval_seconds,
            )
        )
        try:
            await _run_polling_and_worker(dispatcher, bot, worker, stop_runtime)
        finally:
            stop_runtime.set()
            await retention_task
            await diagnostics_task
    finally:
        await bot.session.close()
        await redis_client.aclose()
        await engine.dispose()


async def _run_polling_and_worker(
    dispatcher: Dispatcher,
    bot: Bot,
    worker: QueueWorker,
    stop: Event,
) -> None:
    async with TaskGroup() as tasks:
        tasks.create_task(_run_dispatcher(dispatcher, bot, stop))
        tasks.create_task(_run_worker(worker, stop))


async def _run_dispatcher(dispatcher: Dispatcher, bot: Bot, stop: Event) -> None:
    try:
        await dispatcher.start_polling(bot)
    finally:
        stop.set()


async def _run_worker(worker: QueueWorker, stop: Event) -> None:
    while not stop.is_set():
        await worker.run_once(timeout_seconds=1)


async def _run_retention(
    retention: RetentionSweepService,
    stop: Event,
    *,
    interval_seconds: float,
) -> None:
    if interval_seconds <= 0:
        raise ValueError("interval_seconds must be greater than zero")

    while not stop.is_set():
        try:
            await wait_for(stop.wait(), timeout=interval_seconds)
            return
        except TimeoutError:
            pass

        try:
            result = await retention.sweep()
        except Exception:
            LOGGER.exception("periodic retention sweep failed")
            emit_telemetry(
                LOGGER,
                TelemetryEvent.now(
                    TelemetryEventType.CLEANUP,
                    outcome=OperationOutcome.FAILURE,
                    error_code="retention_sweep_failed",
                    count=0,
                ),
            )
            continue
        _emit_retention_result(result)


async def _run_diagnostics(
    engine: AsyncEngine,
    redis_client: Redis,
    metrics: MetricsRegistry,
    stop: Event,
    *,
    version_name: str,
    environment: str,
    runtime_started: float,
    interval_seconds: float,
) -> None:
    if interval_seconds <= 0:
        raise ValueError("interval_seconds must be greater than zero")

    while not stop.is_set():
        try:
            await wait_for(stop.wait(), timeout=interval_seconds)
            return
        except TimeoutError:
            pass

        try:
            health = await collect_health(engine, redis_client)
            _emit_diagnostics_snapshot(
                health,
                metrics,
                version_name=version_name,
                environment=environment,
                runtime_started=runtime_started,
            )
        except Exception:
            LOGGER.exception("periodic operational diagnostics failed")


def _emit_diagnostics_snapshot(
    health: HealthReport,
    metrics: MetricsRegistry,
    *,
    version_name: str,
    environment: str,
    runtime_started: float,
) -> None:
    emit_admin_diagnostics(
        LOGGER,
        AdminDiagnostics(
            version=version_name,
            environment=environment,
            generated_at=datetime.now(UTC),
            uptime_seconds=max(0.0, monotonic() - runtime_started),
            health=health,
            metrics=metrics.snapshot(),
        ),
    )


def _require_ready_health(health: HealthReport) -> None:
    if not health.ready:
        raise RuntimeError("runtime dependency health check failed")


def _package_version() -> str:
    try:
        return version("simpleconvbot")
    except PackageNotFoundError:
        return "unknown"


def _emit_retention_policy(*, ttl_seconds: int, interval_seconds: int) -> None:
    emit_telemetry(
        LOGGER,
        TelemetryEvent.now(
            TelemetryEventType.RETENTION_POLICY,
            ttl_seconds=ttl_seconds,
            interval_seconds=interval_seconds,
        ),
    )


def _require_complete_initial_retention(result: RetentionSweepResult) -> None:
    _emit_retention_result(result)
    if result.workspaces_failed:
        raise RuntimeError("initial retention sweep reported cleanup failures")


def _emit_retention_result(result: RetentionSweepResult) -> None:
    failed = result.workspaces_failed > 0
    emit_telemetry(
        LOGGER,
        TelemetryEvent.now(
            TelemetryEventType.CLEANUP,
            outcome=OperationOutcome.FAILURE if failed else OperationOutcome.SUCCESS,
            error_code="retention_partial_failure" if failed else None,
            count=result.deleted_total,
        ),
    )
