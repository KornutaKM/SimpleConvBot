import asyncio
from collections.abc import Awaitable
from typing import Any

from aiogram.types import TelegramObject, Update

from simpleconvbot.gateway import UpdateDeduplicationMiddleware


class MemoryReceipts:
    def __init__(self) -> None:
        self.seen: set[int] = set()

    async def claim(self, update_id: int) -> bool:
        if update_id in self.seen:
            return False
        self.seen.add(update_id)
        return True


def test_duplicate_update_is_stopped_before_handler() -> None:
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

    asyncio.run(scenario())
