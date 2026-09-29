from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from uuid import UUID

import pytest

from simpleconvbot.diagnostics import AdminDiagnostics, emit_admin_diagnostics
from simpleconvbot.health import ComponentHealth, HealthReport, HealthState
from simpleconvbot.metrics import MetricsRegistry
from simpleconvbot.telemetry import (
    OperationOutcome,
    OperationStage,
    TelemetryEvent,
    TelemetryEventType,
    emit_operation_telemetry,
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
        error_code="pdf_corrupt",
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
    assert len(snapshot.failure_classes) == 1
    failure = snapshot.failure_classes[0]
    assert failure.operation_id == "pdf.merge"
    assert failure.stage is OperationStage.WORKER
    assert failure.error_code == "pdf_corrupt"
    assert failure.count == 1
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
    registry.record_operation(
        operation_id="image.resize",
        stage=OperationStage.WORKER,
        outcome=OperationOutcome.FAILURE,
        duration_ms=5,
        error_code="image_corrupt",
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
    assert "image_corrupt" in serialized
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


def test_operation_telemetry_updates_aggregate_metrics(
    caplog: pytest.LogCaptureFixture,
) -> None:
    registry = MetricsRegistry()
    event = TelemetryEvent(
        event_type=TelemetryEventType.OPERATION_STAGE,
        timestamp=datetime(2026, 9, 29, 0, 0, tzinfo=UTC),
        operation_id="video.compress",
        stage=OperationStage.WORKER,
        outcome=OperationOutcome.FAILURE,
        duration_ms=42.5,
        error_code="media_timeout",
    )
    logger = logging.getLogger("simpleconvbot.test.metrics")

    with caplog.at_level(logging.INFO, logger=logger.name):
        emit_operation_telemetry(logger, event, registry)

    snapshot = registry.snapshot()
    assert len(snapshot.operations) == 1
    metric = snapshot.operations[0]
    assert metric.operation_id == "video.compress"
    assert metric.stage is OperationStage.WORKER
    assert metric.total == 1
    assert metric.succeeded == 0
    assert metric.failed == 1
    assert metric.duration_sum_ms == 42.5
    assert len(snapshot.failure_classes) == 1
    failure = snapshot.failure_classes[0]
    assert failure.operation_id == "video.compress"
    assert failure.stage is OperationStage.WORKER
    assert failure.error_code == "media_timeout"
    assert failure.count == 1


def test_admin_diagnostics_emit_structured_privacy_safe_json(
    caplog: pytest.LogCaptureFixture,
) -> None:
    registry = MetricsRegistry()
    registry.record_cleanup(deleted=2)
    diagnostics = AdminDiagnostics(
        version="0.1.0.dev0",
        environment="production",
        generated_at=datetime(2026, 9, 29, 0, 0, tzinfo=UTC),
        uptime_seconds=15,
        health=HealthReport(
            components=(
                ComponentHealth("postgres", HealthState.UP, 1),
                ComponentHealth("redis", HealthState.UP, 2),
            )
        ),
        metrics=registry.snapshot(),
    )
    logger = logging.getLogger("simpleconvbot.test.admin")

    with caplog.at_level(logging.INFO, logger=logger.name):
        emit_admin_diagnostics(logger, diagnostics)

    payload = json.loads(caplog.messages[-1])
    assert payload["event"] == "admin_diagnostic"
    assert payload["environment"] == "production"
    assert payload["health"]["ready"] is True
    assert payload["metrics"]["cleanup"]["deleted"] == 2
    serialized = caplog.messages[-1].lower()
    for forbidden in (
        "user_id",
        "chat_id",
        "filename",
        "telegram_file",
        "database_url",
        "redis_url",
        "token",
    ):
        assert forbidden not in serialized


def test_failure_class_metrics_reject_free_form_error_codes() -> None:
    registry = MetricsRegistry()

    with pytest.raises(ValueError, match="stable machine identifier"):
        registry.record_operation(
            operation_id="image.to_png",
            stage=OperationStage.WORKER,
            outcome=OperationOutcome.FAILURE,
            duration_ms=1,
            error_code="unsafe filename: passport.pdf",
        )


def test_failed_operation_telemetry_requires_error_code() -> None:
    event = TelemetryEvent(
        event_type=TelemetryEventType.OPERATION_STAGE,
        timestamp=datetime.now(UTC),
        operation_id="image.to_png",
        stage=OperationStage.WORKER,
        outcome=OperationOutcome.FAILURE,
        duration_ms=1,
    )

    with pytest.raises(ValueError, match="requires error_code"):
        emit_operation_telemetry(logging.getLogger("simpleconvbot.test"), event)


def test_successful_operation_metrics_reject_error_code() -> None:
    registry = MetricsRegistry()

    with pytest.raises(ValueError, match="must not include error_code"):
        registry.record_operation(
            operation_id="image.to_png",
            stage=OperationStage.WORKER,
            outcome=OperationOutcome.SUCCESS,
            duration_ms=1,
            error_code="internal_error",
        )
