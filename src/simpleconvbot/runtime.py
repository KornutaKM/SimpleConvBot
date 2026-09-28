from __future__ import annotations

import logging

from aiogram import Bot
from redis.asyncio import Redis

from simpleconvbot.config import Settings, SettingsError
from simpleconvbot.gateway import create_dispatcher
from simpleconvbot.postgres import (
    PostgresUpdateReceiptStore,
    create_schema,
    make_engine,
    make_session_factory,
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
    dispatcher = create_dispatcher(PostgresUpdateReceiptStore(sessions))

    try:
        await create_schema(engine)
        await redis_client.ping()
        await dispatcher.start_polling(bot)
    finally:
        await bot.session.close()
        await redis_client.aclose()
        await engine.dispose()
