from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import pytest
from redis.asyncio import Redis

from simpleconvbot.redis_sessions import RedisSessionFocusStore


@pytest.mark.integration
def test_session_focus_is_ephemeral_compare_and_delete_routing() -> None:
    asyncio.run(_session_focus_is_ephemeral_compare_and_delete_routing())


async def _session_focus_is_ephemeral_compare_and_delete_routing() -> None:
    client = Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)
    prefix = "test:sessions:focus"
    store = RedisSessionFocusStore(client, prefix=prefix)
    session_id = uuid4()
    other_id = uuid4()
    user_id = 100
    chat_id = -200
    key = f"{prefix}:{user_id}:{chat_id}"

    try:
        await client.delete(key)
        assert await store.get(user_id=user_id, chat_id=chat_id) is None

        await store.set(
            user_id=user_id,
            chat_id=chat_id,
            session_id=session_id,
            ttl_seconds=60,
        )
        assert await store.get(user_id=user_id, chat_id=chat_id) == session_id
        ttl = await client.ttl(key)
        assert 0 < ttl <= 60

        assert not await store.clear(
            user_id=user_id,
            chat_id=chat_id,
            expected_session_id=other_id,
        )
        assert await store.get(user_id=user_id, chat_id=chat_id) == session_id

        assert await store.clear(
            user_id=user_id,
            chat_id=chat_id,
            expected_session_id=session_id,
        )
        assert await store.get(user_id=user_id, chat_id=chat_id) is None

        await client.set(key, "not-a-uuid", ex=60)
        assert await store.get(user_id=user_id, chat_id=chat_id) is None
        assert not await client.exists(key)
    finally:
        await client.delete(key)
        await client.aclose()
