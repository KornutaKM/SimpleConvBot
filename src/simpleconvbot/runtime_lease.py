from __future__ import annotations

from asyncio import Event, sleep, wait_for
from time import monotonic
from uuid import uuid4

from redis.asyncio import Redis

_RENEW_SCRIPT = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('EXPIRE', KEYS[1], ARGV[2])
end
return 0
"""

_RELEASE_SCRIPT = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
end
return 0
"""


class RuntimeLeaseUnavailable(RuntimeError):
    """Raised when another runtime still owns the singleton lease."""


class RuntimeLeaseLost(RuntimeError):
    """Raised when the active runtime can no longer prove lease ownership."""


class RedisRuntimeLease:
    def __init__(
        self,
        client: Redis,
        *,
        key: str = "simpleconvbot:runtime:lease",
        ttl_seconds: int = 30,
        owner_token: str | None = None,
    ) -> None:
        if not key:
            raise ValueError("key must not be empty")
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be greater than zero")
        self._client = client
        self._key = key
        self._ttl_seconds = ttl_seconds
        self._owner_token = owner_token or uuid4().hex

    @property
    def ttl_seconds(self) -> int:
        return self._ttl_seconds

    async def acquire_once(self) -> bool:
        result = await self._client.set(
            self._key,
            self._owner_token,
            nx=True,
            ex=self._ttl_seconds,
        )
        return bool(result)

    async def acquire(
        self,
        *,
        timeout_seconds: float,
        poll_interval_seconds: float = 0.25,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        if poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be greater than zero")

        deadline = monotonic() + timeout_seconds
        while True:
            if await self.acquire_once():
                return

            remaining = deadline - monotonic()
            if remaining <= 0:
                raise RuntimeLeaseUnavailable("runtime lease acquisition timed out")
            await sleep(min(poll_interval_seconds, remaining))

    async def renew(self) -> bool:
        result = await self._client.eval(
            _RENEW_SCRIPT,
            1,
            self._key,
            self._owner_token,
            self._ttl_seconds,
        )
        return int(result or 0) == 1

    async def release(self) -> bool:
        result = await self._client.eval(
            _RELEASE_SCRIPT,
            1,
            self._key,
            self._owner_token,
        )
        return int(result or 0) == 1

    async def maintain(
        self,
        stop: Event,
        *,
        interval_seconds: float | None = None,
    ) -> None:
        interval = interval_seconds or max(1.0, self._ttl_seconds / 3)
        if interval <= 0:
            raise ValueError("interval_seconds must be greater than zero")
        if interval >= self._ttl_seconds:
            raise ValueError("interval_seconds must be shorter than ttl_seconds")

        while not stop.is_set():
            try:
                await wait_for(stop.wait(), timeout=interval)
                return
            except TimeoutError:
                pass

            if not await self.renew():
                raise RuntimeLeaseLost("runtime lease ownership was lost")
