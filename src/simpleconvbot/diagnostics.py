from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from simpleconvbot.health import HealthReport
from simpleconvbot.metrics import MetricsSnapshot


@dataclass(frozen=True, slots=True)
class AdminDiagnostics:
    version: str
    environment: str
    generated_at: datetime
    uptime_seconds: float
    health: HealthReport
    metrics: MetricsSnapshot

    def __post_init__(self) -> None:
        if self.generated_at.tzinfo is None:
            raise ValueError("generated_at must be timezone-aware")
        if self.uptime_seconds < 0:
            raise ValueError("uptime_seconds must be non-negative")

    def to_payload(self) -> dict[str, object]:
        return {
            "version": self.version,
            "environment": self.environment,
            "generated_at": self.generated_at.astimezone(UTC).isoformat(),
            "uptime_seconds": round(self.uptime_seconds, 3),
            "health": self.health.to_payload(),
            "metrics": {
                "operations": [
                    {
                        "operation_id": item.operation_id,
                        "stage": item.stage.value,
                        "total": item.total,
                        "succeeded": item.succeeded,
                        "failed": item.failed,
                        "duration_count": item.duration_count,
                        "duration_sum_ms": item.duration_sum_ms,
                        "duration_max_ms": item.duration_max_ms,
                    }
                    for item in self.metrics.operations
                ],
                "cleanup": {
                    "attempts": self.metrics.cleanup.attempts,
                    "deleted": self.metrics.cleanup.deleted,
                    "failed": self.metrics.cleanup.failed,
                },
            },
        }


def emit_admin_diagnostics(logger: logging.Logger, diagnostics: AdminDiagnostics) -> None:
    payload = {"event": "admin_diagnostic", **diagnostics.to_payload()}
    logger.info(
        json.dumps(
            payload,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
    )
