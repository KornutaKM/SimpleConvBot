from __future__ import annotations

import asyncio
import os

import pytest
from redis.asyncio import Redis

from simpleconvbot.localization import Locale
from simpleconvbot.redis_locale import RedisUserLocaleStore


@pytest.mark.integration
def test_user_locale_hint_is_bounded_and_fail_closed() -> None:
    asyncio.run(_user_locale_hint_is_bounded_and_fail_closed())


async def _user_locale_hint_is_bounded_and_fail_closed() -> None:
    client = Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)
    prefix = "test:ui:locale"
    store = RedisUserLocaleStore(client, ttl_seconds=60, prefix=prefix)
    user_id = 321
    key = f"{prefix}:{user_id}"

    try:
        await client.delete(key)
        assert await store.get(user_id) is None

        await store.remember(user_id, Locale.EN)
        assert await store.get(user_id) is Locale.EN
        ttl = await client.ttl(key)
        assert 0 < ttl <= 60

        await store.remember(user_id, Locale.RU)
        assert await store.get(user_id) is Locale.RU

        await client.set(key, "unsupported-locale", ex=60)
        assert await store.get(user_id) is None
        assert not await client.exists(key)
    finally:
        await client.delete(key)
        await client.aclose()
