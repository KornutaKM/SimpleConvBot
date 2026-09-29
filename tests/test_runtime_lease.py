from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import cast

import pytest
from redis.asyncio import Redis

from simpleconvbot.runtime import _run_runtime_with_lease
from simpleconvbot.runtime_lease import RedisRuntimeLease, RuntimeLeaseLost


class LosingLease:
    def __init__(self, owned_started: asyncio.Event) -> None:
        self._owned_started = owned_started

    async def maintain(self, stop: asyncio.Event) -> None:
        del stop
        await self._owned_started.wait()
        raise RuntimeLeaseLost("runtime lease ownership was lost")


def test_lease_loss_cancels_owned_runtime_and_propagates() -> None:
    async def scenario() -> None:
        stop = asyncio.Event()
        owned_started = asyncio.Event()
        owned_cancelled = asyncio.Event()

        async def owned_runtime() -> None:
            owned_started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                owned_cancelled.set()
                raise

        lease = cast(RedisRuntimeLease, LosingLease(owned_started))

        with pytest.raises(ExceptionGroup) as caught:
            await _run_runtime_with_lease(
                lease,
                stop,
                cast(Callable[[], Awaitable[None]], owned_runtime),
            )

        lease_errors = caught.value.subgroup(RuntimeLeaseLost)
        assert lease_errors is not None
        assert owned_started.is_set()
        assert owned_cancelled.is_set()
        assert stop.is_set()

    asyncio.run(scenario())


def test_lease_maintain_rejects_non_positive_explicit_interval() -> None:
    async def scenario() -> None:
        lease = RedisRuntimeLease(cast(Redis, object()), ttl_seconds=30)

        with pytest.raises(ValueError, match="interval_seconds"):
            await lease.maintain(asyncio.Event(), interval_seconds=0)

    asyncio.run(scenario())
