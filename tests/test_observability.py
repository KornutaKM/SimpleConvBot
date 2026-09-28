from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from uuid import UUID

import pytest

from simpleconvbot.diagnostics import AdminDiagnostics
from simpleconvbot.health import ComponentHealth, HealthReport, HealthState
from simpleconvbot.metrics import MetricsRegistry
from simpleconvbot.telemetry import (
    OperationOutcome,
    OperationStage,
    TelemetryEvent,
    TelemetryEventType,
    emit_telemetry,
    opaque_correlation_id,
)


def test_telemetry_event_contains_only_bounded_machine_fields(
    caplog: pytest.LogCaptureFixture,
) -> None:
    event = TelemetryEvent(
        event_type=TelemetryEventType.OPERATION_STAGE,
        timestamp=datetime(2026, 9, 29, 0, 0, tzinfo=UTC),
        operation_id="image.to_jpeg",
        stage=OperationStage.WORKER,
        outcome=OperationOutcome.FAILURE,
        duration_ms=12.34567,
        error_code="image_corrupt",
        correlation_id="0123456789abcdef",
    )
    logger = logging.getLogger("simpleconvbot.test.telemetry")

    with caplog.at_level(logging.INFO, logger=logger.name):
        emit_telemetry(logger, event)

    payload = json.loads(caplog.messages[-1])
    assert payload == {
        "correlation_id": "0123456789abcdef",
        "duration_ms": 12.346,
        "error_code": "image_corrupt",
        "event": "operation_stage",
        "operation_id": "image.to_jpeg",
        "outcome": "failure",
        "stage": "worker",
        "timestamp": "2026-09-29T00:00:00+00:00",
    }
    serialized = caplog.messages[-1].lower()
    assert "filename" not in serialized
    assert "telegram" not in serialized
    assert "database_url" not in serialized
    assert "redis_url" not in serialized


def test_correlation_id_is_stable_and_does_not_expose_uuid() -> None:
    job_id = UUID("12345678-1234-5678-1234-567812345678")

    first = opaque_correlation_id(job_id)
    second = opaque_correlation_id(job_id)

    assert first == second
    assert len(first) == 16
    assert str(job_id) not in first


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("operation_id", "../../secret"),
        ("error_code", "Bad Error Message"),
    ],
)
def test_telemetry_rejects_free_form_identifiers(field: str, value: str) -> None:
    kwargs: dict[str, object] = {
        "event_type": TelemetryEventType.OPERATION_STAGE,
        "timestamp": datetime.now(UTC),
    }
    kwargs[field] = value

    with pytest.raises(ValueError):
        TelemetryEvent(**kwargs)  # type: ignore[arg-type]


def test_metrics_are_aggregated_without_user_or_file_identity() -> None:
    registry = MetricsRegistry()
    registry.record_operation(
        operation_id="pdf.merge",
        stage=OperationStage.WORKER,
        outcome=OperationOutcome.SUCCESS,
        duration_ms=10,
    )
    registry.record_operation(
        operation_id="pdf.merge",
        stage=OperationStage.WORKER,
        outcome=OperationOutcome.FAILURE,
        duration_ms=30,
    )
    registry.record_cleanup(deleted=3, failed=1)

    snapshot = registry.snapshot()

    assert len(snapshot.operations) == 1
    metric = snapshot.operations[0]
    assert metric.operation_id == "pdf.merge"
    assert metric.total == 2
    assert metric.succeeded == 1
    assert metric.failed == 1
    assert metric.duration_sum_ms == 40
    assert metric.duration_max_ms == 30
    assert snapshot.cleanup.attempts == 1
    assert snapshot.cleanup.deleted == 3
    assert snapshot.cleanup.failed == 1


def test_admin_diagnostics_are_aggregate_only() -> None:
    registry = MetricsRegistry()
    registry.record_operation(
        operation_id="image.resize",
        stage=OperationStage.VALIDATION,
        outcome=OperationOutcome.SUCCESS,
        duration_ms=2,
    )
    diagnostics = AdminDiagnostics(
        version="0.1.0.dev0",
        environment="test",
        generated_at=datetime(2026, 9, 29, 0, 0, tzinfo=UTC),
        uptime_seconds=123.4567,
        health=HealthReport(
            components=(
                ComponentHealth("postgres", HealthState.UP, 1.25),
                ComponentHealth("redis", HealthState.DOWN, 2.5, "TimeoutError"),
            )
        ),
        metrics=registry.snapshot(),
    )

    payload = diagnostics.to_payload()
    serialized = json.dumps(payload, sort_keys=True)

    assert payload["uptime_seconds"] == 123.457
    assert payload["health"]["ready"] is False  # type: ignore[index]
    assert "image.resize" in serialized
    assert "user_id" not in serialized
    assert "chat_id" not in serialized
    assert "filename" not in serialized
    assert "database_url" not in serialized


def test_health_payload_exposes_error_type_not_exception_message() -> None:
    report = HealthReport(
        components=(
            ComponentHealth(
                component="postgres",
                state=HealthState.DOWN,
                latency_ms=5,
                error_type="ConnectionError",
            ),
        )
    )

    payload = report.to_payload()

    assert payload == {
        "ready": False,
        "components": [
            {
                "component": "postgres",
                "state": "down",
                "latency_ms": 5,
                "error_type": "ConnectionError",
            }
        ],
    }
