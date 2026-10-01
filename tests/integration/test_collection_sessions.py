from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime, timedelta

import pytest

from simpleconvbot.postgres import (
    PostgresCollectionSessionRepository,
    create_schema,
    drop_schema,
    make_engine,
    make_session_factory,
)
from simpleconvbot.sessions import (
    SessionAccessDenied,
    SessionEmpty,
    SessionExpired,
    SessionFileInput,
    SessionIdempotencyConflict,
    SessionKind,
    SessionLimitExceeded,
    SessionNotFound,
    SessionPolicy,
    SessionState,
)


@pytest.mark.integration
def test_session_owner_idempotency_order_and_finalize() -> None:
    asyncio.run(_session_owner_idempotency_order_and_finalize())


async def _session_owner_idempotency_order_and_finalize() -> None:
    engine = make_engine(os.environ["DATABASE_URL"])
    sessions = make_session_factory(engine)
    repository = PostgresCollectionSessionRepository(sessions)
    now = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)

    try:
        await drop_schema(engine)
        await create_schema(engine)

        created = await repository.create(
            kind=SessionKind.PDF_MERGE,
            owner_user_id=10,
            chat_id=20,
            now=now,
        )
        assert created.state is SessionState.COLLECTING
        assert created.file_count == 0

        first, first_added = await repository.add_file(
            created.session_id,
            owner_user_id=10,
            chat_id=20,
            item=SessionFileInput(100, "pdf-A", 1000),
            now=now,
        )
        assert first_added
        assert first.file_count == 1

        duplicate, duplicate_added = await repository.add_file(
            created.session_id,
            owner_user_id=10,
            chat_id=20,
            item=SessionFileInput(100, "pdf-A", 1000),
            now=now,
        )
        assert not duplicate_added
        assert duplicate.file_count == 1

        with pytest.raises(SessionIdempotencyConflict):
            await repository.add_file(
                created.session_id,
                owner_user_id=10,
                chat_id=20,
                item=SessionFileInput(100, "different-ref", 1000),
                now=now,
            )

        second, second_added = await repository.add_file(
            created.session_id,
            owner_user_id=10,
            chat_id=20,
            item=SessionFileInput(101, "pdf-B", 2000),
            now=now,
        )
        assert second_added
        assert tuple(item.object_ref for item in second.files) == ("pdf-A", "pdf-B")

        with pytest.raises(SessionAccessDenied):
            await repository.finalize(
                created.session_id,
                owner_user_id=999,
                chat_id=20,
                now=now,
            )

        plan = await repository.finalize(
            created.session_id,
            owner_user_id=10,
            chat_id=20,
            now=now,
        )
        assert plan.operation_id == "pdf.merge"
        assert plan.ordered_input_refs == ("pdf-A", "pdf-B")

        repeated = await repository.finalize(
            created.session_id,
            owner_user_id=10,
            chat_id=20,
            now=now + timedelta(seconds=1),
        )
        assert repeated == plan
    finally:
        await engine.dispose()


@pytest.mark.integration
def test_session_remove_keeps_stable_order_and_monotonic_positions() -> None:
    asyncio.run(_session_remove_keeps_stable_order_and_monotonic_positions())


async def _session_remove_keeps_stable_order_and_monotonic_positions() -> None:
    engine = make_engine(os.environ["DATABASE_URL"])
    sessions = make_session_factory(engine)
    repository = PostgresCollectionSessionRepository(sessions)
    now = datetime(2026, 9, 28, 13, 0, tzinfo=UTC)

    try:
        await drop_schema(engine)
        await create_schema(engine)
        created = await repository.create(
            kind=SessionKind.IMAGES_TO_PDF,
            owner_user_id=1,
            chat_id=2,
            now=now,
        )
        snapshot = created
        for message_id, ref in ((1, "img-A"), (2, "img-B"), (3, "img-C")):
            snapshot, _ = await repository.add_file(
                created.session_id,
                owner_user_id=1,
                chat_id=2,
                item=SessionFileInput(message_id, ref, 100),
                now=now,
            )

        middle = snapshot.files[1]
        removed = await repository.remove_file(
            created.session_id,
            owner_user_id=1,
            chat_id=2,
            file_id=middle.file_id,
            now=now,
        )
        assert tuple(item.object_ref for item in removed.files) == ("img-A", "img-C")
        assert tuple(item.position for item in removed.files) == (1, 3)
        assert removed.file_count == 2
        assert removed.total_bytes == 200

        with pytest.raises(SessionAccessDenied):
            await repository.remove_file(
                created.session_id,
                owner_user_id=999,
                chat_id=2,
                file_id=removed.files[-1].file_id,
                now=now,
            )

        appended, _ = await repository.add_file(
            created.session_id,
            owner_user_id=1,
            chat_id=2,
            item=SessionFileInput(4, "img-D", 100),
            now=now,
        )
        assert tuple(item.object_ref for item in appended.files) == ("img-A", "img-C", "img-D")
        assert tuple(item.position for item in appended.files) == (1, 3, 4)

        plan = await repository.finalize(
            created.session_id,
            owner_user_id=1,
            chat_id=2,
            now=now,
        )
        assert plan.operation_id == "pdf.from_images"
        assert plan.ordered_input_refs == ("img-A", "img-C", "img-D")
    finally:
        await engine.dispose()


@pytest.mark.integration
def test_session_limits_expiry_and_reaper_are_fail_closed() -> None:
    asyncio.run(_session_limits_expiry_and_reaper_are_fail_closed())


async def _session_limits_expiry_and_reaper_are_fail_closed() -> None:
    engine = make_engine(os.environ["DATABASE_URL"])
    sessions = make_session_factory(engine)
    repository = PostgresCollectionSessionRepository(
        sessions,
        SessionPolicy(max_files=2, max_aggregate_bytes=10, ttl_seconds=60),
    )
    now = datetime(2026, 9, 28, 14, 0, tzinfo=UTC)

    try:
        await drop_schema(engine)
        await create_schema(engine)
        created = await repository.create(
            kind=SessionKind.PDF_MERGE,
            owner_user_id=7,
            chat_id=8,
            now=now,
        )

        await repository.add_file(
            created.session_id,
            owner_user_id=7,
            chat_id=8,
            item=SessionFileInput(1, "A", 6),
            now=now,
        )
        with pytest.raises(SessionLimitExceeded):
            await repository.add_file(
                created.session_id,
                owner_user_id=7,
                chat_id=8,
                item=SessionFileInput(2, "too-large", 5),
                now=now,
            )

        await repository.add_file(
            created.session_id,
            owner_user_id=7,
            chat_id=8,
            item=SessionFileInput(2, "B", 4),
            now=now,
        )
        with pytest.raises(SessionLimitExceeded):
            await repository.add_file(
                created.session_id,
                owner_user_id=7,
                chat_id=8,
                item=SessionFileInput(3, "too-many", 1),
                now=now,
            )

        expired_at = now + timedelta(seconds=61)
        with pytest.raises(SessionExpired):
            await repository.finalize(
                created.session_id,
                owner_user_id=7,
                chat_id=8,
                now=expired_at,
            )

        assert await repository.reap_expired(now=expired_at) == 1
        with pytest.raises(SessionNotFound):
            await repository.get_owned(
                created.session_id,
                owner_user_id=7,
                chat_id=8,
            )
    finally:
        await engine.dispose()


@pytest.mark.integration
def test_finalized_session_refs_are_deleted_or_reaped() -> None:
    asyncio.run(_finalized_session_refs_are_deleted_or_reaped())


async def _finalized_session_refs_are_deleted_or_reaped() -> None:
    engine = make_engine(os.environ["DATABASE_URL"])
    sessions = make_session_factory(engine)
    repository = PostgresCollectionSessionRepository(
        sessions,
        SessionPolicy(ttl_seconds=60),
    )
    now = datetime(2026, 9, 28, 15, 0, tzinfo=UTC)

    try:
        await drop_schema(engine)
        await create_schema(engine)

        first = await repository.create(
            kind=SessionKind.IMAGES_TO_PDF,
            owner_user_id=11,
            chat_id=22,
            now=now,
        )
        await repository.add_file(
            first.session_id,
            owner_user_id=11,
            chat_id=22,
            item=SessionFileInput(1, "telegram-file-id-A", 100),
            now=now,
        )
        await repository.finalize(
            first.session_id,
            owner_user_id=11,
            chat_id=22,
            now=now,
        )
        await repository.delete_finalized(
            first.session_id,
            owner_user_id=11,
            chat_id=22,
        )
        with pytest.raises(SessionNotFound):
            await repository.get_owned(
                first.session_id,
                owner_user_id=11,
                chat_id=22,
            )

        second = await repository.create(
            kind=SessionKind.PDF_MERGE,
            owner_user_id=11,
            chat_id=22,
            now=now,
        )
        await repository.add_file(
            second.session_id,
            owner_user_id=11,
            chat_id=22,
            item=SessionFileInput(2, "telegram-file-id-B", 100),
            now=now,
        )
        await repository.finalize(
            second.session_id,
            owner_user_id=11,
            chat_id=22,
            now=now,
        )

        assert await repository.reap_expired(now=now + timedelta(seconds=61)) == 1
        with pytest.raises(SessionNotFound):
            await repository.get_owned(
                second.session_id,
                owner_user_id=11,
                chat_id=22,
            )
    finally:
        await engine.dispose()


@pytest.mark.integration
def test_session_can_remove_final_file_then_accept_new_input() -> None:
    asyncio.run(_session_can_remove_final_file_then_accept_new_input())


async def _session_can_remove_final_file_then_accept_new_input() -> None:
    engine = make_engine(os.environ["DATABASE_URL"])
    sessions = make_session_factory(engine)
    repository = PostgresCollectionSessionRepository(sessions)
    now = datetime(2026, 9, 28, 16, 0, tzinfo=UTC)

    try:
        await drop_schema(engine)
        await create_schema(engine)
        created = await repository.create(
            kind=SessionKind.PDF_MERGE,
            owner_user_id=5,
            chat_id=6,
            now=now,
        )
        one, _ = await repository.add_file(
            created.session_id,
            owner_user_id=5,
            chat_id=6,
            item=SessionFileInput(1, "pdf-A", 123),
            now=now,
        )
        emptied = await repository.remove_file(
            created.session_id,
            owner_user_id=5,
            chat_id=6,
            file_id=one.files[0].file_id,
            now=now,
        )
        assert emptied.state is SessionState.COLLECTING
        assert emptied.file_count == 0
        assert emptied.total_bytes == 0
        assert emptied.files == ()

        with pytest.raises(SessionEmpty):
            await repository.finalize(
                created.session_id,
                owner_user_id=5,
                chat_id=6,
                now=now,
            )

        refilled, added = await repository.add_file(
            created.session_id,
            owner_user_id=5,
            chat_id=6,
            item=SessionFileInput(2, "pdf-B", 456),
            now=now,
        )
        assert added
        assert refilled.file_count == 1
        assert refilled.total_bytes == 456

        plan = await repository.finalize(
            created.session_id,
            owner_user_id=5,
            chat_id=6,
            now=now,
        )
        assert plan.ordered_input_refs == ("pdf-B",)
    finally:
        await engine.dispose()
