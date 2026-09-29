from __future__ import annotations

import logging
from asyncio import Event, create_task

from aiogram import Bot
from aiogram.types import BotCommand
from redis.asyncio import Redis

from simpleconvbot.config import Settings, SettingsError
from simpleconvbot.gateway import create_dispatcher
from simpleconvbot.image_operations import IMAGE_OPERATIONS
from simpleconvbot.jobs import JobAdmissionPolicy
from simpleconvbot.media_operations import MEDIA_OPERATIONS
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
from simpleconvbot.redis_locale import RedisUserLocaleStore\nfrom simpleconvbot.redis_queue import RedisJobQueue
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


async def run_polling(settings: Settings | None = None) -> None:
    current = settings or Settings.from_env()
    current.validate_runtime()
    token = current.telegram_bot_token
    if token is None:
        raise SettingsError("TELEGRAM_BOT_TOKEN is required for bot runtime")

    logging.basicConfig(level=current.log_level)
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
    repository = PostgresJobRepository(
        sessions,
        JobAdmissionPolicy(
            max_active_per_user=current.max_active_jobs_per_user,
            max_active_global=current.max_active_jobs_global,
        ),
    )
    jobs = JobService(repository, queue, registry)
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
    )
    session_policy = SessionPolicy()
    collections = TelegramCollectionGateway(
        bot=bot,
        repository=PostgresCollectionSessionRepository(sessions, session_policy),
        focus=RedisSessionFocusStore(redis_client),
        jobs=jobs,
        storage=storage,
        rate_limiter=rate_limiter,
        locale_store=locale_store,
        policy=session_policy,
    )
    dispatcher = create_dispatcher(
        PostgresUpdateReceiptStore(sessions),
        execution,
        collections,
    )
    delivery = TelegramDelivery(bot, locale_store)
    worker = QueueWorker(
        queue,
        JobWorker(
            repository,
            registry,
            storage,
            TelegramOperationExecutor(storage),
            delivery,
            failure_delivery=delivery,
        ),
    )
    stop_worker = Event()

    try:
        await create_schema(engine)
        await redis_client.ping()
        await queue.recover_inflight()
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
        worker_task = create_task(_run_worker(worker, stop_worker))
        try:
            await dispatcher.start_polling(bot)
        finally:
            stop_worker.set()
            await worker_task
    finally:
        await bot.session.close()
        await redis_client.aclose()
        await engine.dispose()


async def _run_worker(worker: QueueWorker, stop: Event) -> None:
    while not stop.is_set():
        await worker.run_once(timeout_seconds=1)
