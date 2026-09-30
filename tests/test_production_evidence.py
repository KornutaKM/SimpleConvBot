from __future__ import annotations

from simpleconvbot.production_evidence import summarize_lines

COMMIT = "c" * 40
DEPLOYMENT = "deploy-789"


def _healthy_lines() -> list[str]:
    return [
        (
            'prefix {"event":"runtime_identity","provider":"railway",'
            f'"git_commit":"{COMMIT}","deployment_id":"{DEPLOYMENT}",'
            '"replica_id":"replica-1"}'
        ),
        '{"event":"runtime_lease","outcome":"acquired"}',
        '{"event":"recovery_summary","outcome":"success","count":0}',
        '{"event":"retention_policy","ttl_seconds":3600,"interval_seconds":60}',
        '{"event":"cleanup","outcome":"success","count":0}',
        (
            '{"event":"admin_diagnostic","environment":"production",'
            '"health":{"ready":true},"metrics":{"failure_classes":[]}}'
        ),
        '{"event":"runtime_ready"}',
        '{"event":"polling_start"}',
    ]


def test_production_evidence_passes_only_for_exact_deployment() -> None:
    summary = summarize_lines(
        _healthy_lines(),
        expected_commit=COMMIT,
        expected_deployment_id=DEPLOYMENT,
    )

    assert summary["machine_production_ready"] is True
    checks = summary["checks"]
    assert isinstance(checks, dict)
    assert all(item["status"] == "PASS" for item in checks.values())


def test_production_evidence_rejects_commit_or_deployment_mismatch() -> None:
    summary = summarize_lines(
        _healthy_lines(),
        expected_commit="d" * 40,
        expected_deployment_id=DEPLOYMENT,
    )

    assert summary["machine_production_ready"] is False
    checks = summary["checks"]
    assert isinstance(checks, dict)
    assert checks["deployment_identity_matches"]["status"] == "PENDING"


def test_polling_conflict_prevents_machine_ready() -> None:
    lines = [
        *_healthy_lines(),
        "ERROR aiogram TelegramConflictError: terminated by other getUpdates request",
    ]

    summary = summarize_lines(
        lines,
        expected_commit=COMMIT,
        expected_deployment_id=DEPLOYMENT,
    )

    assert summary["machine_production_ready"] is False
    assert summary["polling_conflicts"] == 1
    checks = summary["checks"]
    assert isinstance(checks, dict)
    assert checks["polling_conflict_free"]["status"] == "PENDING"


def test_missing_or_malformed_lines_remain_pending() -> None:
    summary = summarize_lines(
        ["not json", '{"event":"runtime_ready"', '{"event":"polling_start"}'],
        expected_commit=COMMIT,
        expected_deployment_id=DEPLOYMENT,
    )

    assert summary["machine_production_ready"] is False
    checks = summary["checks"]
    assert isinstance(checks, dict)
    assert checks["runtime_ready_observed"]["status"] == "PENDING"
    assert checks["polling_started"]["status"] == "PASS"
