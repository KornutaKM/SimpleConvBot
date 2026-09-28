from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class JobState(StrEnum):
    RECEIVED = "RECEIVED"
    VALIDATING = "VALIDATING"
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    UPLOADING = "UPLOADING"
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


TERMINAL_STATES = frozenset(
    {
        JobState.COMPLETED,
        JobState.REJECTED,
        JobState.FAILED,
        JobState.CANCELLED,
        JobState.EXPIRED,
    }
)

_ALLOWED_TRANSITIONS: dict[JobState, frozenset[JobState]] = {
    JobState.RECEIVED: frozenset({JobState.VALIDATING, JobState.REJECTED, JobState.FAILED}),
    JobState.VALIDATING: frozenset({JobState.QUEUED, JobState.REJECTED, JobState.FAILED}),
    JobState.QUEUED: frozenset(
        {JobState.PROCESSING, JobState.CANCELLED, JobState.EXPIRED, JobState.FAILED}
    ),
    JobState.PROCESSING: frozenset({JobState.UPLOADING, JobState.CANCELLED, JobState.FAILED}),
    JobState.UPLOADING: frozenset({JobState.COMPLETED, JobState.FAILED}),
    JobState.COMPLETED: frozenset(),
    JobState.REJECTED: frozenset(),
    JobState.FAILED: frozenset(),
    JobState.CANCELLED: frozenset(),
    JobState.EXPIRED: frozenset(),
}


class JobError(RuntimeError):
    """Base error for job control-plane failures."""


class JobNotFound(JobError):
    """Raised when a requested job does not exist."""


class InvalidTransition(JobError):
    def __init__(self, current: JobState, target: JobState) -> None:
        super().__init__(f"invalid job transition: {current.value} -> {target.value}")
        self.current = current
        self.target = target


@dataclass(frozen=True, slots=True)
class CreateJob:
    idempotency_key: str
    operation_id: str
    operation_version: int
    user_id: int
    chat_id: int
    source_message_id: int


@dataclass(frozen=True, slots=True)
class JobSnapshot:
    job_id: UUID
    idempotency_key: str
    operation_id: str
    operation_version: int
    user_id: int
    chat_id: int
    source_message_id: int
    state: JobState
    created_at: datetime
    updated_at: datetime


def can_transition(current: JobState, target: JobState) -> bool:
    return target in _ALLOWED_TRANSITIONS[current]


def ensure_transition(current: JobState, target: JobState) -> None:
    if not can_transition(current, target):
        raise InvalidTransition(current, target)
