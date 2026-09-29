from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from uuid import UUID

from simpleconvbot.jobs import CreateJob, JobSnapshot, JobState
from simpleconvbot.operations import OperationDefinition


@dataclass(frozen=True, slots=True)
class LocalizedDeliveryText:
    ru: str
    en: str

    def __post_init__(self) -> None:
        if not self.ru.strip() or not self.en.strip():
            raise ValueError("localized delivery text must not be empty")


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    output_ref: str | None = None
    additional_output_refs: tuple[str, ...] = ()
    delivery_text: LocalizedDeliveryText | None = None

    def __post_init__(self) -> None:
        has_output = self.output_ref is not None
        has_text = self.delivery_text is not None
        if has_output == has_text:
            raise ValueError("execution result must contain either files or delivery text")
        if not has_output and self.additional_output_refs:
            raise ValueError("additional outputs require a primary output")

    @property
    def output_refs(self) -> tuple[str, ...]:
        if self.output_ref is None:
            return ()
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
