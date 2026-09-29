from __future__ import annotations

from uuid import UUID

from redis.asyncio import Redis

_COMPARE_DELETE = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
end
return 0
"""


class RedisSessionFocusStore:
    """Ephemeral routing pointer; PostgreSQL remains authoritative session state."""

    def __init__(
        self,
        client: Redis,
        *,
        prefix: str = "simpleconvbot:sessions:focus",
    ) -> None:
        if not prefix:
            raise ValueError("prefix must not be empty")
        self._client = client
        self._prefix = prefix

    async def set(
        self,
        *,
        user_id: int,
        chat_id: int,
        session_id: UUID,
        ttl_seconds: int,
    ) -> None:
        if user_id <= 0:
            raise ValueError("user_id must be greater than zero")
        if chat_id == 0:
            raise ValueError("chat_id must not be zero")
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be greater than zero")
        await self._client.set(
            self._key(user_id, chat_id),
            str(session_id),
            ex=ttl_seconds,
        )

    async def get(self, *, user_id: int, chat_id: int) -> UUID | None:
        raw = await self._client.get(self._key(user_id, chat_id))
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("ascii", errors="strict")
        try:
            return UUID(str(raw))
        except ValueError:
            await self._client.delete(self._key(user_id, chat_id))
            return None

    async def clear(
        self,
        *,
        user_id: int,
        chat_id: int,
        expected_session_id: UUID | None = None,
    ) -> bool:
        key = self._key(user_id, chat_id)
        if expected_session_id is None:
            return bool(await self._client.delete(key))
        result = await self._client.eval(
            _COMPARE_DELETE,
            1,
            key,
            str(expected_session_id),
        )
        return bool(int(result))

    def _key(self, user_id: int, chat_id: int) -> str:
        return f"{self._prefix}:{user_id}:{chat_id}"
