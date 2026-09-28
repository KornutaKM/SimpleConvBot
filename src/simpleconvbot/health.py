from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from dataclasses import dataclass
from enum import StrEnum
from time import monotonic

from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


class HealthState(StrEnum):
    UP = "up"
    DOWN = "down"


@dataclass(frozen=True, slots=True)
class ComponentHealth:
    component: str
    state: HealthState
    latency_ms: float
    error_type: str | None = None


@dataclass(frozen=True, slots=True)
class HealthReport:
    components: tuple[ComponentHealth, ...]

    @property
    def ready(self) -> bool:
        return bool(self.components) and all(
            component.state is HealthState.UP for component in self.components
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "ready": self.ready,
            "components": [
                {
                    "component": item.component,
                    "state": item.state.value,
                    "latency_ms": round(item.latency_ms, 3),
                    **({"error_type": item.error_type} if item.error_type else {}),
                }
                for item in self.components
            ],
        }


async def collect_health(
    engine: AsyncEngine,
    redis_client: Redis,
    *,
    timeout_seconds: float = 2.0,
) -> HealthReport:
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be greater than zero")

    postgres, redis = await asyncio.gather(
        _probe("postgres", _postgres_ping(engine), timeout_seconds),
        _probe("redis", _redis_ping(redis_client), timeout_seconds),
    )
    return HealthReport(components=(postgres, redis))


async def _postgres_ping(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))


async def _redis_ping(client: Redis) -> None:
    result = await client.ping()
    if result is not True:
        raise RuntimeError("Redis ping returned a non-success result")


async def _probe(
    component: str,
    awaitable: Awaitable[None],
    timeout_seconds: float,
) -> ComponentHealth:
    started = monotonic()
    try:
        await asyncio.wait_for(awaitable, timeout=timeout_seconds)
    except Exception as exc:
        return ComponentHealth(
            component=component,
            state=HealthState.DOWN,
            latency_ms=(monotonic() - started) * 1000,
            error_type=type(exc).__name__,
        )
    return ComponentHealth(
        component=component,
        state=HealthState.UP,
        latency_ms=(monotonic() - started) * 1000,
    )
