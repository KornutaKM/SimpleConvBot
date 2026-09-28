from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware, Dispatcher, Router
from aiogram.filters import CommandStart
from aiogram.types import Message, TelegramObject, Update

from simpleconvbot.ports import UpdateReceiptStore

Handler = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]


class UpdateDeduplicationMiddleware(BaseMiddleware):
    def __init__(self, receipts: UpdateReceiptStore) -> None:
        self._receipts = receipts

    async def __call__(
        self,
        handler: Handler,
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, Update) and not await self._receipts.claim(event.update_id):
            return None
        return await handler(event, data)


def create_router() -> Router:
    router = Router(name="simpleconvbot")

    @router.message(CommandStart())
    async def start(message: Message) -> None:
        await message.answer(
            "SimpleConvBot is running. File conversion operations are enabled "
            "incrementally as their engines pass validation."
        )

    return router


def create_dispatcher(receipts: UpdateReceiptStore) -> Dispatcher:
    dispatcher = Dispatcher()
    dispatcher.update.outer_middleware(UpdateDeduplicationMiddleware(receipts))
    dispatcher.include_router(create_router())
    return dispatcher
