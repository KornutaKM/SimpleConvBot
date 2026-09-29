from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
from enum import StrEnum
import logging
from time import monotonic
from uuid import UUID

from simpleconvbot.jobs import (
    CreateJob,
    InvalidTransition,
    JobSnapshot,
    JobState,
    can_transition,
)
from simpleconvbot.operations import OperationRegistry, UnknownOperation
from simpleconvbot.ports import (
    DeliveryPort,
    FailureDeliveryPort,
    JobQueue,
    JobRepository,
    OperationExecutor,
    TemporaryStorage,
)
from simpleconvbot.telemetry import (
    OperationMetricRecorder,
    OperationOutcome,
    OperationStage,
    TelemetryEvent,
    TelemetryEventType,
    emit_operation_telemetry,
    opaque_correlation_id,
)

LOGGER = logging.getLogger(__name__)



@dataclass(frozen=True, slots=True)
class StartJobRequest:
    user_id: int
    chat_id: int
    source_message_id: int
    operation_id: str
    operation_version: int
    idempotency_token: str | None = None

    @property
    def idempotency_key(self) -> str:
        if self.idempotency_token is not None:
            return (
                f"telegram-session:{self.idempotency_token}:"
                f"{self.operation_id}:v{self.operation_version}"
            )
        return (
            f"telegram:{self.chat_id}:{self.user_id}:{self.source_message_id}:"
            f"{self.operation_id}:v{self.operation_version}"
        )


@dataclass(frozen=True, slots=True)
class StartJobResult:
    job: JobSnapshot
    created: bool


class JobService:
    def __init__(
        self,
        repository: JobRepository,
        queue: JobQueue,
        registry: OperationRegistry,
        metrics: OperationMetricRecorder | None = None,
    ) -> None:
        self._repository = repository
        self._queue = queue
        self._registry = registry
        self._metrics = metrics

    async def start_operation(
        self,
        request: StartJobRequest,
        *,
        prepare: Callable[[JobSnapshot], Awaitable[None]] | None = None,
    ) -> StartJobResult:
        job, created = await self._repository.create_or_get(
            CreateJob(
                idempotency_key=request.idempotency_key,
                operation_id=request.operation_id,
                operation_version=request.operation_version,
                user_id=request.user_id,
                chat_id=request.chat_id,
                source_message_id=request.source_message_id,
            )
        )

        if job.state is JobState.RECEIVED:
            job = await self._repository.transition(
                job.job_id,
                JobState.RECEIVED,
                JobState.VALIDATING,
            )

        if job.state is JobState.VALIDATING:
            try:
                self._registry.get(job.operation_id, job.operation_version)
                if prepare is not None:
                    await prepare(job)
            except UnknownOperation:
                job = await self._repository.transition(
                    job.job_id,
                    JobState.VALIDATING,
                    JobState.REJECTED,
                )
                return StartJobResult(job=job, created=created)
            except Exception:
                job = await self._repository.transition(
                    job.job_id,
                    JobState.VALIDATING,
                    JobState.FAILED,
                )
                raise
            job = await self._repository.transition(
                job.job_id,
                JobState.VALIDATING,
                JobState.QUEUED,
            )

        if job.state is JobState.QUEUED:
            queue_started = monotonic()
            try:
                await self._queue.enqueue(job.job_id)
            except Exception as exc:
                _emit_stage(
                    job,
                    OperationStage.QUEUE,
                    OperationOutcome.FAILURE,
                    queue_started,
                    metrics=self._metrics,
                    error_code=_exception_code(exc),
                )
                with suppress(InvalidTransition):
                    job = await self._repository.transition(
                        job.job_id,
                        JobState.QUEUED,
                        JobState.FAILED,
                    )
                raise
            _emit_stage(
                job,
                OperationStage.QUEUE,
                OperationOutcome.SUCCESS,
                queue_started,
                metrics=self._metrics,
            )

        return StartJobResult(job=job, created=created)


class WorkerOutcome(StrEnum):
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class JobWorker:
    def __init__(
        self,
        repository: JobRepository,
        registry: OperationRegistry,
        storage: TemporaryStorage,
        executor: OperationExecutor,
        delivery: DeliveryPort,
        failure_delivery: FailureDeliveryPort | None = None,
        metrics: OperationMetricRecorder | None = None,
    ) -> None:
        self._repository = repository
        self._registry = registry
        self._storage = storage
        self._executor = executor
        self._delivery = delivery
        self._failure_delivery = failure_delivery
        self._metrics = metrics

    async def process(self, job_id: UUID) -> WorkerOutcome:
        job = await self._repository.get(job_id)
        if job.state is not JobState.QUEUED:
            return WorkerOutcome.SKIPPED

        try:
            job = await self._repository.transition(
                job_id,
                JobState.QUEUED,
                JobState.PROCESSING,
            )
        except InvalidTransition:
            return WorkerOutcome.SKIPPED

        try:
            operation = self._registry.get(job.operation_id, job.operation_version)
            workspace = await self._storage.ensure_workspace(job_id)
            result = await self._executor.execute(job, operation, workspace)
            job = await self._repository.transition(
                job_id,
                JobState.PROCESSING,
                JobState.UPLOADING,
            )
            await self._delivery.deliver(job, result)
            await _cleanup_workspace(
                self._storage,
                job,
                metrics=self._metrics,
                suppress_errors=False,
            )
            await self._repository.transition(
                job_id,
                JobState.UPLOADING,
                JobState.COMPLETED,
            )
        except Exception as exc:
            await _cleanup_workspace(
                self._storage,
                job,
                metrics=self._metrics,
                suppress_errors=True,
            )

            current = await self._repository.get(job_id)
            failed = current
            if can_transition(current.state, JobState.FAILED):
                with suppress(InvalidTransition):
                    failed = await self._repository.transition(
                        job_id,
                        current.state,
                        JobState.FAILED,
                    )

            if self._failure_delivery is not None:
                with suppress(Exception):
                    await self._failure_delivery.deliver_failure(
                        failed,
                        _exception_code(exc),
                    )
            return WorkerOutcome.FAILED

        return WorkerOutcome.COMPLETED


class QueueWorker:
    def __init__(self, queue: JobQueue, worker: JobWorker) -> None:
        self._queue = queue
        self._worker = worker

    async def run_once(self, timeout_seconds: int = 1) -> bool:
        job_id = await self._queue.reserve(timeout_seconds)
        if job_id is None:
            return False
        await self._worker.process(job_id)
        await self._queue.ack(job_id)
        return True


async def _cleanup_workspace(
    storage: TemporaryStorage,
    job: JobSnapshot,
    *,
    metrics: OperationMetricRecorder | None,
    suppress_errors: bool,
) -> None:
    started = monotonic()
    try:
        await storage.cleanup_workspace(job.job_id)
    except Exception as exc:
        _emit_stage(
            job,
            OperationStage.CLEANUP,
            OperationOutcome.FAILURE,
            started,
            metrics=metrics,
            error_code=_exception_code(exc),
        )
        if not suppress_errors:
            raise
        return
    _emit_stage(
        job,
        OperationStage.CLEANUP,
        OperationOutcome.SUCCESS,
        started,
        metrics=metrics,
    )


def _emit_stage(
    job: JobSnapshot,
    stage: OperationStage,
    outcome: OperationOutcome,
    started: float,
    *,
    metrics: OperationMetricRecorder | None,
    error_code: str | None = None,
) -> None:
    emit_operation_telemetry(
        LOGGER,
        TelemetryEvent.now(
            TelemetryEventType.OPERATION_STAGE,
            operation_id=job.operation_id,
            stage=stage,
            outcome=outcome,
            duration_ms=(monotonic() - started) * 1000,
            error_code=error_code,
            correlation_id=opaque_correlation_id(job.job_id),
        ),
        metrics,
    )


def _exception_code(exc: Exception) -> str:
    code = getattr(exc, "code", "internal_error")
    value = getattr(code, "value", code)
    return value if isinstance(value, str) else "internal_error"
