from __future__ import annotations

import asyncio
import os

import pytest

from simpleconvbot.jobs import (
    CreateJob,
    JobAdmissionCode,
    JobAdmissionPolicy,
    JobAdmissionRejected,
    JobState,
)
from simpleconvbot.postgres import (
    PostgresJobRepository,
    create_schema,
    drop_schema,
    make_engine,
    make_session_factory,
)


def _command(index: int, *, user_id: int) -> CreateJob:
    return CreateJob(
        idempotency_key=f"admission:{user_id}:{index}",
        operation_id="test.noop",
        operation_version=1,
        user_id=user_id,
        chat_id=1000 + user_id,
        source_message_id=index,
    )


@pytest.mark.integration
def test_idempotent_repeat_does_not_consume_another_user_slot() -> None:
    asyncio.run(_idempotent_repeat_does_not_consume_another_user_slot())


async def _idempotent_repeat_does_not_consume_another_user_slot() -> None:
    engine = make_engine(os.environ["DATABASE_URL"])
    sessions = make_session_factory(engine)
    repository = PostgresJobRepository(
        sessions,
        JobAdmissionPolicy(max_active_per_user=1, max_active_global=10),
    )

    try:
        await drop_schema(engine)
        await create_schema(engine)

        first, created = await repository.create_or_get(_command(1, user_id=1))
        repeated, repeated_created = await repository.create_or_get(_command(1, user_id=1))

        assert created
        assert not repeated_created
        assert repeated.job_id == first.job_id

        with pytest.raises(JobAdmissionRejected) as captured:
            await repository.create_or_get(_command(2, user_id=1))
        assert captured.value.code is JobAdmissionCode.USER_CONCURRENCY
    finally:
        await engine.dispose()


@pytest.mark.integration
def test_global_active_job_limit_is_enforced() -> None:
    asyncio.run(_global_active_job_limit_is_enforced())


async def _global_active_job_limit_is_enforced() -> None:
    engine = make_engine(os.environ["DATABASE_URL"])
    sessions = make_session_factory(engine)
    repository = PostgresJobRepository(
        sessions,
        JobAdmissionPolicy(max_active_per_user=1, max_active_global=1),
    )

    try:
        await drop_schema(engine)
        await create_schema(engine)

        await repository.create_or_get(_command(1, user_id=1))
        with pytest.raises(JobAdmissionRejected) as captured:
            await repository.create_or_get(_command(1, user_id=2))
        assert captured.value.code is JobAdmissionCode.GLOBAL_CONCURRENCY
    finally:
        await engine.dispose()


@pytest.mark.integration
def test_terminal_job_releases_admission_capacity() -> None:
    asyncio.run(_terminal_job_releases_admission_capacity())


async def _terminal_job_releases_admission_capacity() -> None:
    engine = make_engine(os.environ["DATABASE_URL"])
    sessions = make_session_factory(engine)
    repository = PostgresJobRepository(
        sessions,
        JobAdmissionPolicy(max_active_per_user=1, max_active_global=1),
    )

    try:
        await drop_schema(engine)
        await create_schema(engine)

        first, _ = await repository.create_or_get(_command(1, user_id=1))
        state = first
        for target in (
            JobState.VALIDATING,
            JobState.QUEUED,
            JobState.PROCESSING,
            JobState.UPLOADING,
            JobState.COMPLETED,
        ):
            state = await repository.transition(state.job_id, state.state, target)

        second, created = await repository.create_or_get(_command(2, user_id=1))
        assert created
        assert second.state is JobState.RECEIVED
    finally:
        await engine.dispose()


@pytest.mark.integration
def test_concurrent_same_user_creates_only_one_active_job() -> None:
    asyncio.run(_concurrent_same_user_creates_only_one_active_job())


async def _concurrent_same_user_creates_only_one_active_job() -> None:
    engine = make_engine(os.environ["DATABASE_URL"])
    sessions = make_session_factory(engine)
    repository = PostgresJobRepository(
        sessions,
        JobAdmissionPolicy(max_active_per_user=1, max_active_global=10),
    )

    try:
        await drop_schema(engine)
        await create_schema(engine)

        async def attempt(index: int) -> bool:
            try:
                _, created = await repository.create_or_get(_command(index, user_id=7))
                return created
            except JobAdmissionRejected as exc:
                assert exc.code is JobAdmissionCode.USER_CONCURRENCY
                return False

        results = await asyncio.gather(attempt(1), attempt(2))
        assert sorted(results) == [False, True]
    finally:
        await engine.dispose()
