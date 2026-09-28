from __future__ import annotations

import asyncio
import os

import pytest
from redis.asyncio import Redis

from simpleconvbot.health import HealthState, collect_health
from simpleconvbot.postgres import make_engine


@pytest.mark.integration
def test_live_postgres_and_redis_health_is_ready() -> None:
    asyncio.run(_live_postgres_and_redis_health_is_ready())


async def _live_postgres_and_redis_health_is_ready() -> None:
    engine = make_engine(os.environ["DATABASE_URL"])
    redis_client = Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)

    try:
        report = await collect_health(engine, redis_client, timeout_seconds=2)
    finally:
        await redis_client.aclose()
        await engine.dispose()

    assert report.ready
    assert {component.component for component in report.components} == {"postgres", "redis"}
    assert all(component.state is HealthState.UP for component in report.components)
    assert all(component.error_type is None for component in report.components)
    assert all(component.latency_ms >= 0 for component in report.components)
