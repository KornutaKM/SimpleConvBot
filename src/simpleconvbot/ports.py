from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from uuid import UUID

from simpleconvbot.jobs import CreateJob, JobSnapshot, JobState
from simpleconvbot.operations import OperationDefinition


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    output_ref: str
    additional_output_refs: tuple[str, ...] = ()

    @property
    def output_refs(self) -> tuple[str, ...]:
        return (self.output_ref, *self.additional_output_refs)


class UpdateReceiptStore(Protocol):
    async def claim(self, update_id: int) -> bool: ...


class JobRepository(Protocol):
    async def create_or_get(self, command: CreateJob) -> tuple[JobSnapshot, bool]: ...

    async def get(self, job_id: UUID) -> JobSnapshot: ...

    async def transition(
        self,
        job_id: UUID,
        expected: JobState,
        target: JobState,
    ) -> JobSnapshot: ...


class JobQueue(Protocol):
    async def enqueue(self, job_id: UUID) -> None: ...

    async def reserve(self, timeout_seconds: int) -> UUID | None: ...

    async def ack(self, job_id: UUID) -> None: ...

    async def recover_inflight(self) -> int: ...


class TemporaryStorage(Protocol):
    async def ensure_workspace(self, job_id: UUID) -> Path: ...

    async def cleanup_workspace(self, job_id: UUID) -> None: ...


class OperationExecutor(Protocol):
    async def execute(
        self,
        job: JobSnapshot,
        operation: OperationDefinition,
        workspace: Path,
    ) -> ExecutionResult: ...


class DeliveryPort(Protocol):
    async def deliver(self, job: JobSnapshot, result: ExecutionResult) -> None: ...


class FailureDeliveryPort(Protocol):
    async def deliver_failure(self, job: JobSnapshot, error_code: str) -> None: ...
