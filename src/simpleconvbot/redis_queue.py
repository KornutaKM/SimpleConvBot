from __future__ import annotations

from typing import cast
from uuid import UUID

from redis.asyncio import Redis


class RedisJobQueue:
    def __init__(self, client: Redis, prefix: str = "simpleconvbot:jobs") -> None:
        self._client = client
        self._ready = f"{prefix}:ready"
        self._processing = f"{prefix}:processing"

    async def enqueue(self, job_id: UUID) -> None:
        await self._client.lpush(self._ready, str(job_id))

    async def reserve(self, timeout_seconds: int) -> UUID | None:
        raw = await self._client.brpoplpush(
            self._ready,
            self._processing,
            timeout=timeout_seconds,
        )
        if raw is None:
            return None
        return _job_id(raw)

    async def ack(self, job_id: UUID) -> None:
        await self._client.lrem(self._processing, 1, str(job_id))

    async def recover_inflight(self) -> int:
        recovered = 0
        while True:
            raw = await self._client.rpoplpush(self._processing, self._ready)
            if raw is None:
                return recovered
            _job_id(raw)
            recovered += 1


def _job_id(raw: object) -> UUID:
    if isinstance(raw, bytes):
        return UUID(raw.decode("utf-8"))
    return UUID(cast(str, raw))
