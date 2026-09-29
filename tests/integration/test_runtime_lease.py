from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import pytest
from redis.asyncio import Redis

from simpleconvbot.runtime_lease import RedisRuntimeLease


@pytest.mark.integration
def test_runtime_lease_is_exclusive_and_owner_safe() -> None:
    asyncio.run(_runtime_lease_is_exclusive_and_owner_safe())


async def _runtime_lease_is_exclusive_and_owner_safe() -> None:
    client = Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)
    key = f"test:runtime:lease:{uuid4()}"
    first = RedisRuntimeLease(client, key=key, ttl_seconds=5)
    second = RedisRuntimeLease(client, key=key, ttl_seconds=5)
    try:
        assert await first.acquire_once()
        assert not await second.acquire_once()
        assert await first.renew()
        assert not await second.renew()
        assert not await second.release()
        assert await first.release()
        assert await second.acquire_once()
        assert await second.release()
    finally:
        await client.delete(key)
        await client.aclose()


@pytest.mark.integration
def test_runtime_lease_transfers_after_ttl_expiry() -> None:
    asyncio.run(_runtime_lease_transfers_after_ttl_expiry())


async def _runtime_lease_transfers_after_ttl_expiry() -> None:
    client = Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)
    key = f"test:runtime:lease:{uuid4()}"
    first = RedisRuntimeLease(client, key=key, ttl_seconds=1)
    second = RedisRuntimeLease(client, key=key, ttl_seconds=1)
    try:
        assert await first.acquire_once()
        await asyncio.sleep(1.1)
        assert await second.acquire_once()
        assert not await first.release()
        assert await second.release()
    finally:
        await client.delete(key)
        await client.aclose()
