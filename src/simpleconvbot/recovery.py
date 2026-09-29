from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from simpleconvbot.jobs import JobSnapshot, JobState
from simpleconvbot.localization import UserErrorCode
from simpleconvbot.telemetry import (
    OperationOutcome,
    TelemetryEvent,
    TelemetryEventType,
    emit_telemetry,
    opaque_correlation_id,
)

LOGGER = logging.getLogger(__name__)

_INTERRUPTED_STATES = frozenset(
    {
        JobState.RECEIVED,
        JobState.VALIDATING,
        JobState.PROCESSING,
        JobState.UPLOADING,
    }
)


class RecoveryRepository(Protocol):
    async def list_active_for_recovery(self) -> tuple[JobSnapshot, ...]: ...

    async def transition(
        self,
        job_id: UUID,
        expected: JobState,
        target: JobState,
    ) -> JobSnapshot: ...


class RecoveryQueue(Protocol):
    async def enqueue(self, job_id: UUID) -> None: ...

    async def recover_inflight(self) -> int: ...


class RecoveryStorage(Protocol):
    async def cleanup_workspace(self, job_id: UUID) -> None: ...


class RecoveryFailureDelivery(Protocol):
    async def deliver_failure(self, job: JobSnapshot, error_code: str) -> None: ...


@dataclass(frozen=True, slots=True)
class StartupRecoveryResult:
    inflight_queue_items: int
    interrupted_failed: int
    queued_reenqueued: int


class StartupRecoveryService:
    def __init__(
        self,
        *,
        repository: RecoveryRepository,
        queue: RecoveryQueue,
        storage: RecoveryStorage,
        failure_delivery: RecoveryFailureDelivery | None = None,
    ) -> None:
        self._repository = repository
        self._queue = queue
        self._storage = storage
        self._failure_delivery = failure_delivery

    async def recover(self) -> StartupRecoveryResult:
        inflight_queue_items = await self._queue.recover_inflight()
        active = await self._repository.list_active_for_recovery()

        interrupted = tuple(job for job in active if job.state in _INTERRUPTED_STATES)
        queued = tuple(job for job in active if job.state is JobState.QUEUED)

        unexpected = tuple(
            job
            for job in active
            if job.state not in _INTERRUPTED_STATES and job.state is not JobState.QUEUED
        )
        if unexpected:
            raise RuntimeError("startup recovery observed an unexpected active job state")

        failed_count = 0
        for job in interrupted:
            await self._storage.cleanup_workspace(job.job_id)
            failed = await self._repository.transition(job.job_id, job.state, JobState.FAILED)
            failed_count += 1
            _emit_recovery(
                failed, OperationOutcome.FAILURE, UserErrorCode.RESTART_INTERRUPTED.value
            )
            await self._notify_interrupted(failed)

        requeued_count = 0
        for job in queued:
            await self._queue.enqueue(job.job_id)
            requeued_count += 1
            _emit_recovery(job, OperationOutcome.SUCCESS)

        if inflight_queue_items:
            emit_telemetry(
                LOGGER,
                TelemetryEvent.now(
                    TelemetryEventType.RECOVERY,
                    outcome=OperationOutcome.SUCCESS,
                    count=inflight_queue_items,
                ),
            )

        result = StartupRecoveryResult(
            inflight_queue_items=inflight_queue_items,
            interrupted_failed=failed_count,
            queued_reenqueued=requeued_count,
        )
        emit_telemetry(
            LOGGER,
            TelemetryEvent.now(
                TelemetryEventType.RECOVERY_SUMMARY,
                outcome=OperationOutcome.SUCCESS,
                count=(
                    result.inflight_queue_items
                    + result.interrupted_failed
                    + result.queued_reenqueued
                ),
            ),
        )
        return result

    async def _notify_interrupted(self, job: JobSnapshot) -> None:
        if self._failure_delivery is None:
            return
        try:
            await self._failure_delivery.deliver_failure(
                job,
                UserErrorCode.RESTART_INTERRUPTED.value,
            )
        except Exception:
            LOGGER.exception("restart recovery failure notification failed")


def _emit_recovery(
    job: JobSnapshot,
    outcome: OperationOutcome,
    error_code: str | None = None,
) -> None:
    emit_telemetry(
        LOGGER,
        TelemetryEvent.now(
            TelemetryEventType.RECOVERY,
            operation_id=job.operation_id,
            outcome=outcome,
            error_code=error_code,
            correlation_id=opaque_correlation_id(job.job_id),
        ),
    )
