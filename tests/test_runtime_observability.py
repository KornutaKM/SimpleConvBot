from __future__ import annotations

import json
import logging
from time import monotonic

import pytest

from simpleconvbot.health import ComponentHealth, HealthReport, HealthState
from simpleconvbot.metrics import MetricsRegistry
from simpleconvbot.runtime import _emit_diagnostics_snapshot, _require_ready_health


def test_startup_health_gate_accepts_ready_dependencies() -> None:
    report = HealthReport(
        components=(
            ComponentHealth("postgres", HealthState.UP, 1),
            ComponentHealth("redis", HealthState.UP, 2),
        )
    )

    _require_ready_health(report)


def test_startup_health_gate_rejects_dependency_failure() -> None:
    report = HealthReport(
        components=(
            ComponentHealth("postgres", HealthState.UP, 1),
            ComponentHealth("redis", HealthState.DOWN, 2, "TimeoutError"),
        )
    )

    with pytest.raises(RuntimeError, match="dependency health"):
        _require_ready_health(report)


def test_runtime_diagnostics_snapshot_is_aggregate_only(
    caplog: pytest.LogCaptureFixture,
) -> None:
    metrics = MetricsRegistry()
    report = HealthReport(
        components=(
            ComponentHealth("postgres", HealthState.UP, 1),
            ComponentHealth("redis", HealthState.UP, 2),
        )
    )
    logger_name = "simpleconvbot.runtime"

    with caplog.at_level(logging.INFO, logger=logger_name):
        _emit_diagnostics_snapshot(
            report,
            metrics,
            version_name="0.1.0.dev0",
            environment="test",
            runtime_started=monotonic(),
        )

    payload = json.loads(caplog.messages[-1])
    assert payload["event"] == "admin_diagnostic"
    assert payload["health"]["ready"] is True
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
