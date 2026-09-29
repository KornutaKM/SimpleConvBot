from __future__ import annotations

import json
import logging
import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import blake2b
from typing import Protocol
from uuid import UUID

_SAFE_ID = re.compile(r"^[a-z0-9]+(?:[._:-][a-z0-9]+)*$")


class OperationStage(StrEnum):
    VALIDATION = "validation"
    QUEUE = "queue"
    WORKER = "worker"
    UPLOAD = "upload"
    CLEANUP = "cleanup"


class OperationOutcome(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"


class OperationMetricRecorder(Protocol):
    def record_operation(
        self,
        *,
        operation_id: str,
        stage: OperationStage,
        outcome: OperationOutcome,
        duration_ms: float,
        error_code: str | None = None,
    ) -> None: ...


class TelemetryEventType(StrEnum):
    OPERATION_STAGE = "operation_stage"
    HEALTH = "health"
    CLEANUP = "cleanup"
    ADMIN_DIAGNOSTIC = "admin_diagnostic"
    RECOVERY = "recovery"
    RECOVERY_SUMMARY = "recovery_summary"
    UPDATE_DEDUPLICATED = "update_deduplicated"


@dataclass(frozen=True, slots=True)
class TelemetryEvent:
    event_type: TelemetryEventType
    timestamp: datetime
    operation_id: str | None = None
    stage: OperationStage | None = None
    outcome: OperationOutcome | None = None
    duration_ms: float | None = None
    error_code: str | None = None
    correlation_id: str | None = None
    count: int | None = None

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ValueError("telemetry timestamp must be timezone-aware")
        if self.operation_id is not None:
            _validate_safe_id("operation_id", self.operation_id)
        if self.error_code is not None:
            _validate_safe_id("error_code", self.error_code)
        if self.correlation_id is not None and not re.fullmatch(
            r"[0-9a-f]{16}", self.correlation_id
        ):
            raise ValueError("correlation_id must be a 16-character hex token")
        if self.duration_ms is not None and (
            not math.isfinite(self.duration_ms) or self.duration_ms < 0
        ):
            raise ValueError("duration_ms must be finite and non-negative")
        if self.count is not None and self.count < 0:
            raise ValueError("count must be non-negative")

    @classmethod
    def now(
        cls,
        event_type: TelemetryEventType,
        *,
        operation_id: str | None = None,
        stage: OperationStage | None = None,
        outcome: OperationOutcome | None = None,
        duration_ms: float | None = None,
        error_code: str | None = None,
        correlation_id: str | None = None,
        count: int | None = None,
    ) -> TelemetryEvent:
        return cls(
            event_type=event_type,
            timestamp=datetime.now(UTC),
            operation_id=operation_id,
            stage=stage,
            outcome=outcome,
            duration_ms=duration_ms,
            error_code=error_code,
            correlation_id=correlation_id,
            count=count,
        )

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "event": self.event_type.value,
            "timestamp": self.timestamp.astimezone(UTC).isoformat(),
        }
        if self.operation_id is not None:
            payload["operation_id"] = self.operation_id
        if self.stage is not None:
            payload["stage"] = self.stage.value
        if self.outcome is not None:
            payload["outcome"] = self.outcome.value
        if self.duration_ms is not None:
            payload["duration_ms"] = round(self.duration_ms, 3)
        if self.error_code is not None:
            payload["error_code"] = self.error_code
        if self.correlation_id is not None:
            payload["correlation_id"] = self.correlation_id
        if self.count is not None:
            payload["count"] = self.count
        return payload

    def to_json(self) -> str:
        return json.dumps(
            self.to_payload(),
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )


def opaque_correlation_id(job_id: UUID) -> str:
    return blake2b(job_id.bytes, digest_size=8, person=b"scb-alpha").hexdigest()


def emit_telemetry(logger: logging.Logger, event: TelemetryEvent) -> None:
    logger.info(event.to_json())


def emit_operation_telemetry(
    logger: logging.Logger,
    event: TelemetryEvent,
    metrics: OperationMetricRecorder | None = None,
) -> None:
    if (
        event.event_type is not TelemetryEventType.OPERATION_STAGE
        or event.operation_id is None
        or event.stage is None
        or event.outcome is None
        or event.duration_ms is None
    ):
        raise ValueError("operation telemetry requires operation_id, stage, outcome, and duration")
    if event.outcome is OperationOutcome.FAILURE and event.error_code is None:
        raise ValueError("failed operation telemetry requires error_code")
    if event.outcome is OperationOutcome.SUCCESS and event.error_code is not None:
        raise ValueError("successful operation telemetry must not include error_code")
    if metrics is not None:
        metrics.record_operation(
            operation_id=event.operation_id,
            stage=event.stage,
            outcome=event.outcome,
            duration_ms=event.duration_ms,
            error_code=event.error_code,
        )
    emit_telemetry(logger, event)


def _validate_safe_id(name: str, value: str) -> None:
    if len(value) > 128 or _SAFE_ID.fullmatch(value) is None:
        raise ValueError(f"{name} must be a stable machine identifier")
