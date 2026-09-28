from __future__ import annotations

from redis.asyncio import Redis

_RATE_LIMIT_SCRIPT = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[2])
end
if current > tonumber(ARGV[1]) then
    return 0
end
return 1
"""


class RedisUpdateRateLimiter:
    def __init__(
        self,
        client: Redis,
        *,
        limit: int = 60,
        window_seconds: int = 60,
        prefix: str = "simpleconvbot:security:update-rate",
    ) -> None:
        if limit <= 0:
            raise ValueError("limit must be greater than zero")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be greater than zero")
        if not prefix:
            raise ValueError("prefix must not be empty")
        self._client = client
        self._limit = limit
        self._window_seconds = window_seconds
        self._prefix = prefix

    async def allow(self, user_id: int) -> bool:
        if user_id <= 0:
            raise ValueError("user_id must be greater than zero")
        key = f"{self._prefix}:{user_id}"
        result = await self._client.eval(
            _RATE_LIMIT_SCRIPT,
            1,
            key,
            self._limit,
            self._window_seconds,
        )
        return int(result) == 1
