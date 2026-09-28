from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta, datetime
from enum import StrEnum
from uuid import UUID


class SessionKind(StrEnum):
    IMAGES_TO_PDF = "images_to_pdf"
    PDF_MERGE = "pdf_merge"

    @property
    def operation_id(self) -> str:
        return {
            SessionKind.IMAGES_TO_PDF: "pdf.from_images",
            SessionKind.PDF_MERGE: "pdf.merge",
        }[self]


class SessionState(StrEnum):
    COLLECTING = "COLLECTING"
    FINALIZED = "FINALIZED"


class SessionError(RuntimeError):
    """Base error for multi-file collection sessions."""


class SessionNotFound(SessionError):
    """Raised when a collection session does not exist."""


class SessionAccessDenied(SessionError):
    """Raised when owner/chat identity does not match the collection session."""


class SessionExpired(SessionError):
    """Raised when a collecting session is past its expiry."""


class SessionClosed(SessionError):
    """Raised when a finalized session is mutated."""


class SessionEmpty(SessionError):
    """Raised when finalization is attempted without files."""


class SessionLimitExceeded(SessionError):
    """Raised when file-count or aggregate-size policy would be exceeded."""


class SessionFileNotFound(SessionError):
    """Raised when a requested file is not part of the session."""


class SessionIdempotencyConflict(SessionError):
    """Raised when one Telegram message identity maps to conflicting file metadata."""


@dataclass(frozen=True, slots=True)
class SessionPolicy:
    max_files: int = 20
    max_aggregate_bytes: int = 40 * 1024 * 1024
    ttl_seconds: int = 60 * 60

    def __post_init__(self) -> None:
        if self.max_files <= 0:
            raise ValueError("max_files must be greater than zero")
        if self.max_aggregate_bytes <= 0:
            raise ValueError("max_aggregate_bytes must be greater than zero")
        if self.ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be greater than zero")

    @property
    def ttl(self) -> timedelta:
        return timedelta(seconds=self.ttl_seconds)


@dataclass(frozen=True, slots=True)
class SessionFileInput:
    source_message_id: int
    object_ref: str
    byte_size: int

    def __post_init__(self) -> None:
        if self.source_message_id <= 0:
            raise ValueError("source_message_id must be greater than zero")
        if not self.object_ref or len(self.object_ref) > 512:
            raise ValueError("object_ref must contain 1..512 characters")
        if self.byte_size <= 0:
            raise ValueError("byte_size must be greater than zero")


@dataclass(frozen=True, slots=True)
class SessionFileSnapshot:
    file_id: UUID
    source_message_id: int
    object_ref: str
    byte_size: int
    position: int


@dataclass(frozen=True, slots=True)
class CollectionSessionSnapshot:
    session_id: UUID
    kind: SessionKind
    state: SessionState
    owner_user_id: int
    chat_id: int
    expires_at: datetime
    file_count: int
    total_bytes: int
    files: tuple[SessionFileSnapshot, ...]
    created_at: datetime
    updated_at: datetime

    @property
    def operation_id(self) -> str:
        return self.kind.operation_id


@dataclass(frozen=True, slots=True)
class FinalizedSessionPlan:
    session_id: UUID
    kind: SessionKind
    operation_id: str
    files: tuple[SessionFileSnapshot, ...]

    @property
    def ordered_input_refs(self) -> tuple[str, ...]:
        return tuple(item.object_ref for item in self.files)


def finalization_plan(snapshot: CollectionSessionSnapshot) -> FinalizedSessionPlan:
    if snapshot.state is not SessionState.FINALIZED:
        raise SessionClosed("session must be finalized before building an execution plan")
    if not snapshot.files:
        raise SessionEmpty("finalized session has no files")
    ordered = tuple(sorted(snapshot.files, key=lambda item: item.position))
    return FinalizedSessionPlan(
        session_id=snapshot.session_id,
        kind=snapshot.kind,
        operation_id=snapshot.operation_id,
        files=ordered,
    )
