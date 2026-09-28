from __future__ import annotations

import math
import re
from dataclasses import dataclass
from threading import Lock

from simpleconvbot.telemetry import OperationOutcome, OperationStage

_OPERATION_ID = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")


@dataclass(frozen=True, slots=True)
class OperationMetricSnapshot:
    operation_id: str
    stage: OperationStage
    total: int
    succeeded: int
    failed: int
    duration_count: int
    duration_sum_ms: float
    duration_max_ms: float


@dataclass(frozen=True, slots=True)
class CleanupMetricSnapshot:
    attempts: int
    deleted: int
    failed: int


@dataclass(frozen=True, slots=True)
class MetricsSnapshot:
    operations: tuple[OperationMetricSnapshot, ...]
    cleanup: CleanupMetricSnapshot


@dataclass(slots=True)
class _OperationAggregate:
    total: int = 0
    succeeded: int = 0
    failed: int = 0
    duration_count: int = 0
    duration_sum_ms: float = 0.0
    duration_max_ms: float = 0.0


class MetricsRegistry:
    def __init__(self) -> None:
        self._lock = Lock()
        self._operations: dict[tuple[str, OperationStage], _OperationAggregate] = {}
        self._cleanup_attempts = 0
        self._cleanup_deleted = 0
        self._cleanup_failed = 0

    def record_operation(
        self,
        *,
        operation_id: str,
        stage: OperationStage,
        outcome: OperationOutcome,
        duration_ms: float,
    ) -> None:
        if len(operation_id) > 128 or _OPERATION_ID.fullmatch(operation_id) is None:
            raise ValueError("operation_id must be a stable lowercase identifier")
        if not math.isfinite(duration_ms) or duration_ms < 0:
            raise ValueError("duration_ms must be finite and non-negative")

        key = (operation_id, stage)
        with self._lock:
            aggregate = self._operations.setdefault(key, _OperationAggregate())
            aggregate.total += 1
            if outcome is OperationOutcome.SUCCESS:
                aggregate.succeeded += 1
            else:
                aggregate.failed += 1
            aggregate.duration_count += 1
            aggregate.duration_sum_ms += duration_ms
            aggregate.duration_max_ms = max(aggregate.duration_max_ms, duration_ms)

    def record_cleanup(self, *, deleted: int = 0, failed: int = 0) -> None:
        if deleted < 0 or failed < 0:
            raise ValueError("cleanup counters must be non-negative")
        with self._lock:
            self._cleanup_attempts += 1
            self._cleanup_deleted += deleted
            self._cleanup_failed += failed

    def snapshot(self) -> MetricsSnapshot:
        with self._lock:
            operation_items = tuple(
                OperationMetricSnapshot(
                    operation_id=operation_id,
                    stage=stage,
                    total=aggregate.total,
                    succeeded=aggregate.succeeded,
                    failed=aggregate.failed,
                    duration_count=aggregate.duration_count,
                    duration_sum_ms=round(aggregate.duration_sum_ms, 3),
                    duration_max_ms=round(aggregate.duration_max_ms, 3),
                )
                for (operation_id, stage), aggregate in sorted(
                    self._operations.items(),
                    key=lambda item: (item[0][0], item[0][1].value),
                )
            )
            cleanup = CleanupMetricSnapshot(
                attempts=self._cleanup_attempts,
                deleted=self._cleanup_deleted,
                failed=self._cleanup_failed,
            )
        return MetricsSnapshot(operations=operation_items, cleanup=cleanup)
