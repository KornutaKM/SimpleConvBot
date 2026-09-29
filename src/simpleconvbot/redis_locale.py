from __future__ import annotations

from redis.asyncio import Redis

from simpleconvbot.localization import Locale


class RedisUserLocaleStore:
    """Ephemeral locale hint for queued Telegram delivery; not product authority."""

    def __init__(
        self,
        client: Redis,
        *,
        ttl_seconds: int = 24 * 60 * 60,
        prefix: str = "simpleconvbot:ui:locale",
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be greater than zero")
        if not prefix:
            raise ValueError("prefix must not be empty")
        self._client = client
        self._ttl_seconds = ttl_seconds
        self._prefix = prefix

    async def remember(self, user_id: int, locale: Locale) -> None:
        if user_id <= 0:
            raise ValueError("user_id must be greater than zero")
        await self._client.set(
            self._key(user_id),
            locale.value,
            ex=self._ttl_seconds,
        )

    async def get(self, user_id: int) -> Locale | None:
        if user_id <= 0:
            raise ValueError("user_id must be greater than zero")
        key = self._key(user_id)
        raw = await self._client.get(key)
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("ascii", errors="strict")
        try:
            return Locale(str(raw))
        except ValueError:
            await self._client.delete(key)
            return None

    def _key(self, user_id: int) -> str:
        return f"{self._prefix}:{user_id}"
