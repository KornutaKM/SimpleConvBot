from __future__ import annotations

import asyncio
from typing import cast

import pytest
from aiogram import Bot, Dispatcher

from simpleconvbot.runtime import _run_polling_and_worker
from simpleconvbot.services import QueueWorker


class CrashingWorker:
    async def run_once(self, timeout_seconds: int = 1) -> bool:
        del timeout_seconds
        raise RuntimeError("queue backend failed")


class BlockingDispatcher:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.cancelled = asyncio.Event()

    async def start_polling(self, *bots: Bot, **kwargs: object) -> None:
        del bots, kwargs
        self.started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancelled.set()
            raise


def test_worker_failure_cancels_polling_and_propagates() -> None:
    async def scenario() -> None:
        stop = asyncio.Event()
        dispatcher = BlockingDispatcher()
        worker = CrashingWorker()

        with pytest.raises(ExceptionGroup) as caught:
            await _run_polling_and_worker(
                cast(Dispatcher, dispatcher),
                cast(Bot, object()),
                cast(QueueWorker, worker),
                stop,
            )

        runtime_errors = caught.value.subgroup(RuntimeError)
        assert runtime_errors is not None
        assert any(
            isinstance(exc, RuntimeError) and str(exc) == "queue backend failed"
            for exc in runtime_errors.exceptions
        )
        assert dispatcher.started.is_set()
        assert dispatcher.cancelled.is_set()
        assert stop.is_set()

    asyncio.run(scenario())
