import asyncio
import json
import logging
from collections.abc import Awaitable
from typing import Any

import pytest
from aiogram.types import TelegramObject, Update

from simpleconvbot.gateway import UpdateDeduplicationMiddleware, create_router


class MemoryReceipts:
    def __init__(self) -> None:
        self.seen: set[int] = set()

    async def claim(self, update_id: int) -> bool:
        if update_id in self.seen:
            return False
        self.seen.add(update_id)
        return True


def test_duplicate_update_is_stopped_before_handler(
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def scenario() -> None:
        receipts = MemoryReceipts()
        middleware = UpdateDeduplicationMiddleware(receipts)
        calls = 0

        async def handler(event: TelegramObject, data: dict[str, Any]) -> None:
            nonlocal calls
            del event, data
            calls += 1

        event = Update(update_id=42)
        callback: Awaitable[Any]

        callback = middleware(handler, event, {})
        await callback
        callback = middleware(handler, event, {})
        await callback

        assert calls == 1

    with caplog.at_level(logging.INFO, logger="simpleconvbot.gateway"):
        asyncio.run(scenario())

    payloads = [
        json.loads(message)
        for message in caplog.messages
        if '"event":"update_deduplicated"' in message
    ]
    assert len(payloads) == 1
    assert payloads[0]["count"] == 1
    assert payloads[0]["outcome"] == "success"
    serialized = json.dumps(payloads[0], sort_keys=True)
    assert "update_id" not in serialized
    assert "user_id" not in serialized
    assert "chat_id" not in serialized


def test_router_registers_help_callback_handler() -> None:
    router = create_router()

    callback_names = {handler.callback.__name__ for handler in router.callback_query.handlers}

    assert "help" in callback_names


def test_router_registers_help_message_command() -> None:
    router = create_router()

    message_names = {handler.callback.__name__ for handler in router.message.handlers}

    assert "help_command" in message_names


def test_router_registers_resize_callback_handlers() -> None:
    router = create_router()

    callback_names = {handler.callback.__name__ for handler in router.callback_query.handlers}

    assert "show_image_resize" in callback_names
    assert "back_from_image_resize" in callback_names
    assert "execute_image_resize" in callback_names


def test_router_registers_compression_callback_handlers() -> None:
    router = create_router()

    callback_names = {handler.callback.__name__ for handler in router.callback_query.handlers}

    assert "show_image_compress" in callback_names
    assert "back_from_image_compress" in callback_names
    assert "execute_image_compress" in callback_names
