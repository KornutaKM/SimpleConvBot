from __future__ import annotations

import asyncio
import os

import pytest
from redis.asyncio import Redis

from simpleconvbot.redis_security import RedisUpdateRateLimiter


@pytest.mark.integration
def test_redis_rate_limit_is_atomic_and_user_scoped() -> None:
    asyncio.run(_redis_rate_limit_is_atomic_and_user_scoped())


async def _redis_rate_limit_is_atomic_and_user_scoped() -> None:
    client = Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)
    try:
        await client.flushdb()
        limiter = RedisUpdateRateLimiter(
            client,
            limit=2,
            window_seconds=60,
            prefix="test:security:update-rate",
        )

        assert await limiter.allow(100)
        assert await limiter.allow(100)
        assert not await limiter.allow(100)
        assert await limiter.allow(200)

        ttl = await client.ttl("test:security:update-rate:100")
        assert 0 < ttl <= 60
    finally:
        await client.aclose()
