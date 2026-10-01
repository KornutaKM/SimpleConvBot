from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

import simpleconvbot.production_review as production_review
from simpleconvbot.production_review import (
    CHECK_IDS,
    MACHINE_IMPORT_CHECK_IDS,
    import_machine_evidence,
    load_review,
    mark_review,
    new_review,
    review_summary,
    save_review,
)

COMMIT = "1" * 40
OTHER_COMMIT = "2" * 40
DEPLOYMENT = "deploy-123"


def _healthy_machine_lines(
    *,
    commit: str = COMMIT,
    deployment_id: str = DEPLOYMENT,
) -> list[str]:
    return [
        (
            '{"event":"runtime_identity","provider":"railway",'
            f'"git_commit":"{commit}","deployment_id":"{deployment_id}",'
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


def _checks(review: dict[str, object]) -> dict[str, object]:
    value = review["checks"]
    assert isinstance(value, dict)
    return cast(dict[str, object], value)


def test_production_review_starts_pending_and_is_commit_bound() -> None:
    review = new_review(
        commit_sha=COMMIT,
        provider="railway",
        deployment_id="deploy-123",
        runtime_identity="sha256:abcdef",
    )

    summary = review_summary(review, expected_commit=COMMIT)

    assert summary["commit_matches"] is True
    assert summary["release_ready"] is False
    assert summary["status"] == "PENDING"
    assert summary["passed"] == 0
    assert summary["failed"] == []
    assert summary["pending"] == list(CHECK_IDS)


def test_production_review_requires_every_check_and_exact_commit() -> None:
    review = new_review(
        commit_sha=COMMIT,
        provider="railway",
        deployment_id="deploy-123",
        runtime_identity="sha256:abcdef",
    )
    for check_id in CHECK_IDS:
        mark_review(review, check_id=check_id, status="pass")

    complete = review_summary(review, expected_commit=COMMIT)
    assert complete["release_ready"] is True
    assert complete["status"] == "PASS"
    assert complete["passed"] == len(CHECK_IDS)

    stale = review_summary(review, expected_commit=OTHER_COMMIT)
    assert stale["commit_matches"] is False
    assert stale["release_ready"] is False


def test_fail_or_pending_keeps_release_closed() -> None:
    review = new_review(
        commit_sha=COMMIT,
        provider="railway",
        deployment_id="deploy-123",
        runtime_identity="sha256:abcdef",
    )
    for check_id in CHECK_IDS:
        mark_review(review, check_id=check_id, status="pass")
    mark_review(review, check_id="provider_alerts_enabled", status="fail")

    summary = review_summary(review, expected_commit=COMMIT)

    assert summary["release_ready"] is False
    assert summary["failed"] == ["provider_alerts_enabled"]


def test_round_trip_rejects_extra_private_fields(tmp_path: Path) -> None:
    path = tmp_path / "production-review.json"
    review = new_review(
        commit_sha=COMMIT,
        provider="railway",
        deployment_id="deploy-123",
        runtime_identity="sha256:abcdef",
    )
    save_review(path, review)
    assert load_review(path) == review

    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["database_url"] = "postgresql://secret"
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ValueError, match="unexpected or missing"):
        load_review(path)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("deployment_id", "contains spaces"),
        ("deployment_id", "https://user:secret@example.invalid"),
        ("runtime_identity", "contains/slash"),
    ],
)
def test_identity_fields_are_bounded(field: str, value: str) -> None:
    kwargs = {
        "commit_sha": COMMIT,
        "provider": "railway",
        "deployment_id": "deploy-123",
        "runtime_identity": "sha256:abcdef",
    }
    kwargs[field] = value
    with pytest.raises(ValueError, match="bounded machine identifier"):
        new_review(**kwargs)


def test_require_ready_exit_code_is_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "production-review.json"
    review = new_review(
        commit_sha=COMMIT,
        provider="railway",
        deployment_id="deploy-123",
        runtime_identity="sha256:abcdef",
    )
    save_review(path, review)
    monkeypatch.setattr(production_review, "current_git_commit", lambda: COMMIT)

    assert production_review.main(["show", "--input", str(path), "--require-ready"]) == 2

    for check_id in CHECK_IDS:
        mark_review(review, check_id=check_id, status="pass")
    save_review(path, review)

    assert production_review.main(["show", "--input", str(path), "--require-ready"]) == 0


def test_machine_import_marks_only_machine_owned_checks() -> None:
    review = new_review(
        commit_sha=COMMIT,
        provider="railway",
        deployment_id=DEPLOYMENT,
        runtime_identity="sha256:abcdef",
    )
    mark_review(review, check_id="provider_alerts_enabled", status="fail")

    summary = import_machine_evidence(
        review,
        evidence_lines=_healthy_machine_lines(),
        expected_commit=COMMIT,
    )

    assert summary["machine_production_ready"] is True
    checks = _checks(review)
    assert {check_id for check_id in CHECK_IDS if checks[check_id] == "pass"} == set(
        MACHINE_IMPORT_CHECK_IDS
    )
    assert checks["provider_alerts_enabled"] == "fail"
    assert checks["backup_policy_confirmed"] == "pending"
    assert review_summary(review, expected_commit=COMMIT)["release_ready"] is False


def test_machine_import_refuses_stale_review_commit() -> None:
    review = new_review(
        commit_sha=COMMIT,
        provider="railway",
        deployment_id=DEPLOYMENT,
        runtime_identity="sha256:abcdef",
    )

    with pytest.raises(ValueError, match="does not match current git HEAD"):
        import_machine_evidence(
            review,
            evidence_lines=_healthy_machine_lines(commit=OTHER_COMMIT),
            expected_commit=OTHER_COMMIT,
        )

    assert all(value == "pending" for value in _checks(review).values())


def test_machine_import_refuses_mismatched_deployment() -> None:
    review = new_review(
        commit_sha=COMMIT,
        provider="railway",
        deployment_id=DEPLOYMENT,
        runtime_identity="sha256:abcdef",
    )

    with pytest.raises(ValueError, match="machine evidence is not ready"):
        import_machine_evidence(
            review,
            evidence_lines=_healthy_machine_lines(deployment_id="deploy-other"),
            expected_commit=COMMIT,
        )

    assert all(value == "pending" for value in _checks(review).values())


def test_machine_import_refuses_polling_conflict() -> None:
    review = new_review(
        commit_sha=COMMIT,
        provider="railway",
        deployment_id=DEPLOYMENT,
        runtime_identity="sha256:abcdef",
    )
    lines = [
        *_healthy_machine_lines(),
        "ERROR TelegramConflictError: terminated by other getUpdates request",
    ]

    with pytest.raises(ValueError, match="machine evidence is not ready"):
        import_machine_evidence(
            review,
            evidence_lines=lines,
            expected_commit=COMMIT,
        )

    assert all(value == "pending" for value in _checks(review).values())


def test_import_machine_cli_writes_only_machine_checks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    review_path = tmp_path / "production-review.json"
    evidence_path = tmp_path / "production-runtime.log"
    review = new_review(
        commit_sha=COMMIT,
        provider="railway",
        deployment_id=DEPLOYMENT,
        runtime_identity="sha256:abcdef",
    )
    save_review(review_path, review)
    evidence_path.write_text("\n".join(_healthy_machine_lines()) + "\n", encoding="utf-8")
    monkeypatch.setattr(production_review, "current_git_commit", lambda: COMMIT)

    assert (
        production_review.main(
            [
                "import-machine",
                "--input",
                str(review_path),
                "--evidence",
                str(evidence_path),
            ]
        )
        == 0
    )

    imported = load_review(review_path)
    checks = _checks(imported)
    assert {check_id for check_id in CHECK_IDS if checks[check_id] == "pass"} == set(
        MACHINE_IMPORT_CHECK_IDS
    )
