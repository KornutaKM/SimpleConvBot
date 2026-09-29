from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from simpleconvbot.jobs import InvalidTransition, JobSnapshot, JobState
from simpleconvbot.localization import UserErrorCode
from simpleconvbot.recovery import StartupRecoveryService


class FakeRepository:
    def __init__(self, jobs: tuple[JobSnapshot, ...]) -> None:
        self.jobs = {job.job_id: job for job in jobs}
        self.transitions: list[tuple[UUID, JobState, JobState]] = []

    async def list_active_for_recovery(self) -> tuple[JobSnapshot, ...]:
        return tuple(self.jobs.values())

    async def transition(
        self,
        job_id: UUID,
        expected: JobState,
        target: JobState,
    ) -> JobSnapshot:
        current = self.jobs[job_id]
        if current.state is not expected:
            raise InvalidTransition(current.state, target)
        updated = JobSnapshot(
            job_id=current.job_id,
            idempotency_key=current.idempotency_key,
            operation_id=current.operation_id,
            operation_version=current.operation_version,
            user_id=current.user_id,
            chat_id=current.chat_id,
            source_message_id=current.source_message_id,
            state=target,
            created_at=current.created_at,
            updated_at=current.updated_at,
        )
        self.jobs[job_id] = updated
        self.transitions.append((job_id, expected, target))
        return updated


class FakeQueue:
    def __init__(self, inflight: int = 0) -> None:
        self.inflight = inflight
        self.enqueued: list[UUID] = []
        self.recover_calls = 0

    async def recover_inflight(self) -> int:
        self.recover_calls += 1
        return self.inflight

    async def enqueue(self, job_id: UUID) -> None:
        self.enqueued.append(job_id)


class FakeStorage:
    def __init__(self, fail_job_id: UUID | None = None) -> None:
        self.fail_job_id = fail_job_id
        self.cleaned: list[UUID] = []

    async def cleanup_workspace(self, job_id: UUID) -> None:
        self.cleaned.append(job_id)
        if job_id == self.fail_job_id:
            raise RuntimeError("synthetic cleanup failure")


class RecordingFailureDelivery:
    def __init__(self) -> None:
        self.calls: list[tuple[UUID, str]] = []

    async def deliver_failure(self, job: JobSnapshot, error_code: str) -> None:
        self.calls.append((job.job_id, error_code))


def test_startup_recovery_fails_interrupted_jobs_and_requeues_queued_jobs() -> None:
    asyncio.run(_startup_recovery_fails_interrupted_jobs_and_requeues_queued_jobs())


async def _startup_recovery_fails_interrupted_jobs_and_requeues_queued_jobs() -> None:
    queued = _job(JobState.QUEUED, "image.to_png")
    interrupted = (
        _job(JobState.RECEIVED, "image.to_jpeg"),
        _job(JobState.VALIDATING, "pdf.to_images"),
        _job(JobState.PROCESSING, "video.compress"),
        _job(JobState.UPLOADING, "audio.to_mp3"),
    )
    repository = FakeRepository((queued, *interrupted))
    queue = FakeQueue(inflight=2)
    storage = FakeStorage()
    delivery = RecordingFailureDelivery()

    result = await StartupRecoveryService(
        repository=repository,
        queue=queue,
        storage=storage,
        failure_delivery=delivery,
    ).recover()

    assert result.inflight_queue_items == 2
    assert result.interrupted_failed == 4
    assert result.queued_reenqueued == 1
    assert queue.recover_calls == 1
    assert queue.enqueued == [queued.job_id]
    assert set(storage.cleaned) == {job.job_id for job in interrupted}
    assert repository.jobs[queued.job_id].state is JobState.QUEUED
    for job in interrupted:
        assert repository.jobs[job.job_id].state is JobState.FAILED
    assert {job_id for job_id, _ in delivery.calls} == {job.job_id for job in interrupted}
    assert {code for _, code in delivery.calls} == {UserErrorCode.RESTART_INTERRUPTED.value}


def test_startup_recovery_emits_privacy_safe_summary(
    caplog: pytest.LogCaptureFixture,
) -> None:
    queued = _job(JobState.QUEUED, "image.to_png")
    interrupted = _job(JobState.PROCESSING, "video.compress")
    service = StartupRecoveryService(
        repository=FakeRepository((queued, interrupted)),
        queue=FakeQueue(inflight=2),
        storage=FakeStorage(),
        failure_delivery=RecordingFailureDelivery(),
    )

    with caplog.at_level(logging.INFO, logger="simpleconvbot.recovery"):
        result = asyncio.run(service.recover())

    assert result.inflight_queue_items == 2
    assert result.interrupted_failed == 1
    assert result.queued_reenqueued == 1
    summaries = [
        json.loads(message)
        for message in caplog.messages
        if '"event":"recovery_summary"' in message
    ]
    assert len(summaries) == 1
    assert summaries[0]["count"] == 4
    assert summaries[0]["outcome"] == "success"
    serialized = json.dumps(summaries[0], sort_keys=True)
    for forbidden in ("job_id", "user_id", "chat_id", "source_message_id"):
        assert forbidden not in serialized


def test_cleanup_failure_keeps_interrupted_job_active_and_aborts_recovery() -> None:
    asyncio.run(_cleanup_failure_keeps_interrupted_job_active_and_aborts_recovery())


async def _cleanup_failure_keeps_interrupted_job_active_and_aborts_recovery() -> None:
    processing = _job(JobState.PROCESSING, "video.to_gif")
    queued = _job(JobState.QUEUED, "image.to_webp")
    repository = FakeRepository((processing, queued))
    queue = FakeQueue()
    storage = FakeStorage(fail_job_id=processing.job_id)

    with pytest.raises(RuntimeError, match="synthetic cleanup failure"):
        await StartupRecoveryService(
            repository=repository,
            queue=queue,
            storage=storage,
        ).recover()

    assert repository.jobs[processing.job_id].state is JobState.PROCESSING
    assert repository.transitions == []
    assert queue.enqueued == []


def _job(state: JobState, operation_id: str) -> JobSnapshot:
    now = datetime.now(UTC)
    return JobSnapshot(
        job_id=uuid4(),
        idempotency_key=f"test:{uuid4()}",
        operation_id=operation_id,
        operation_version=1,
        user_id=1,
        chat_id=2,
        source_message_id=3,
        state=state,
        created_at=now,
        updated_at=now,
    )
