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
from simpleconvbot.operations import OperationRegistry
from simpleconvbot.postgres import (
    PostgresJobRepository,
    PostgresUpdateReceiptStore,
    create_schema,
    make_engine,
    make_session_factory,
)
from simpleconvbot.redis_queue import RedisJobQueue
from simpleconvbot.redis_security import RedisUpdateRateLimiter
from simpleconvbot.services import JobService, JobWorker, QueueWorker
from simpleconvbot.storage import LocalTemporaryStorage
from simpleconvbot.telegram_execution import (
    TelegramDelivery,
    TelegramExecutionGateway,
    TelegramImageExecutor,
)


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
    registry = OperationRegistry(IMAGE_OPERATIONS)
    queue = RedisJobQueue(redis_client)
    jobs = JobService(
        PostgresJobRepository(
            sessions,
            JobAdmissionPolicy(
                max_active_per_user=current.max_active_jobs_per_user,
                max_active_global=current.max_active_jobs_global,
            ),
        ),
        queue,
        registry,
    )
    execution = TelegramExecutionGateway(
        bot=bot,
        jobs=jobs,
        storage=storage,
        rate_limiter=RedisUpdateRateLimiter(
            redis_client,
            limit=current.update_rate_limit_per_minute,
        ),
    )
    dispatcher = create_dispatcher(PostgresUpdateReceiptStore(sessions), execution)
    worker = QueueWorker(
        queue,
        JobWorker(
            PostgresJobRepository(sessions),
            registry,
            storage,
            TelegramImageExecutor(storage),
            TelegramDelivery(bot),
        ),
    )
    stop_worker = Event()

    try:
        await create_schema(engine)
        await redis_client.ping()
        await queue.recover_inflight()
        await bot.set_my_commands(
            [
                BotCommand(command="start", description="Главный экран"),
                BotCommand(command="tools", description="Все инструменты"),
                BotCommand(command="settings", description="Настройки"),
            ]
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
