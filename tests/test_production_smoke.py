from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

import simpleconvbot.production_smoke as production_smoke
from simpleconvbot.production_review import (
    CHECK_IDS as REVIEW_CHECK_IDS,
)
from simpleconvbot.production_review import (
    load_review,
    mark_review,
    new_review,
    save_review,
)
from simpleconvbot.production_smoke import (
    ADVERTISED_OPERATION_IDS,
    CHECK_IDS,
    NON_ADVERTISED_OPERATION_IDS,
    apply_smoke_to_review,
    load_smoke,
    mark_smoke,
    new_smoke,
    save_smoke,
    smoke_summary,
)
from simpleconvbot.production_smoke import (
    REVIEW_CHECK_IDS as SMOKE_REVIEW_CHECK_IDS,
)

COMMIT = "a" * 40
OTHER_COMMIT = "b" * 40
DEPLOYMENT = "deploy-123"
RUNTIME = "sha256:abcdef"


def _review() -> dict[str, object]:
    return new_review(
        commit_sha=COMMIT,
        provider="railway",
        deployment_id=DEPLOYMENT,
        runtime_identity=RUNTIME,
    )


def _checks(manifest: dict[str, object]) -> dict[str, object]:
    checks = manifest["checks"]
    assert isinstance(checks, dict)
    return cast(dict[str, object], checks)


def _complete(smoke: dict[str, object]) -> None:
    for check_id in CHECK_IDS:
        mark_smoke(smoke, check_id=check_id, status="pass")


def test_smoke_manifest_covers_every_product_operation_except_legacy_aliases() -> None:
    assert {"image.compress", "video.compress"} == NON_ADVERTISED_OPERATION_IDS
    assert len(ADVERTISED_OPERATION_IDS) == 30
    assert len(set(ADVERTISED_OPERATION_IDS)) == 30
    assert "pdf.from_images" in ADVERTISED_OPERATION_IDS
    assert "pdf.merge" in ADVERTISED_OPERATION_IDS
    assert "pdf.extract_first" in ADVERTISED_OPERATION_IDS
    assert "pdf.extract_first_5" in ADVERTISED_OPERATION_IDS
    assert "pdf.extract_last" in ADVERTISED_OPERATION_IDS
    assert "all" not in CHECK_IDS
    assert len(CHECK_IDS) == 37


def test_new_smoke_is_bound_to_review_and_starts_pending() -> None:
    smoke = new_smoke(review=_review(), expected_commit=COMMIT)

    summary = smoke_summary(smoke, expected_commit=COMMIT)

    assert summary["commit_matches"] is True
    assert summary["advertised_operation_checks"] == 30
    assert summary["passed"] == 0
    assert summary["failed"] == []
    assert summary["pending"] == list(CHECK_IDS)
    assert summary["smoke_ready"] is False
    assert smoke["deployment_id"] == DEPLOYMENT
    assert smoke["runtime_identity"] == RUNTIME


def test_new_smoke_refuses_stale_review() -> None:
    with pytest.raises(ValueError, match="does not match current git HEAD"):
        new_smoke(review=_review(), expected_commit=OTHER_COMMIT)


def test_smoke_requires_every_individual_check() -> None:
    smoke = new_smoke(review=_review(), expected_commit=COMMIT)
    for check_id in CHECK_IDS[:-1]:
        mark_smoke(smoke, check_id=check_id, status="pass")

    incomplete = smoke_summary(smoke, expected_commit=COMMIT)
    assert incomplete["smoke_ready"] is False
    assert incomplete["pending"] == [CHECK_IDS[-1]]

    mark_smoke(smoke, check_id=CHECK_IDS[-1], status="pass")
    complete = smoke_summary(smoke, expected_commit=COMMIT)
    assert complete["smoke_ready"] is True
    assert complete["passed"] == len(CHECK_IDS)


def test_failed_smoke_remains_closed() -> None:
    smoke = new_smoke(review=_review(), expected_commit=COMMIT)
    _complete(smoke)
    mark_smoke(smoke, check_id="cleanup.after_failure", status="fail")

    summary = smoke_summary(smoke, expected_commit=COMMIT)

    assert summary["smoke_ready"] is False
    assert summary["failed"] == ["cleanup.after_failure"]


def test_apply_refuses_incomplete_smoke_without_mutating_review() -> None:
    review = _review()
    smoke = new_smoke(review=review, expected_commit=COMMIT)
    mark_smoke(smoke, check_id=CHECK_IDS[0], status="pass")

    with pytest.raises(ValueError, match="production smoke is not ready"):
        apply_smoke_to_review(smoke, review, expected_commit=COMMIT)

    assert all(value == "pending" for value in _checks(review).values())


def test_apply_refuses_binding_mismatch() -> None:
    review = _review()
    smoke = new_smoke(review=review, expected_commit=COMMIT)
    _complete(smoke)
    smoke["deployment_id"] = "deploy-other"

    with pytest.raises(ValueError, match="binding does not match"):
        apply_smoke_to_review(smoke, review, expected_commit=COMMIT)

    assert all(value == "pending" for value in _checks(review).values())


def test_apply_marks_only_smoke_owned_review_checks() -> None:
    review = _review()
    mark_review(review, check_id="provider_alerts_enabled", status="fail")
    smoke = new_smoke(review=review, expected_commit=COMMIT)
    _complete(smoke)

    apply_smoke_to_review(smoke, review, expected_commit=COMMIT)

    review_checks = _checks(review)
    passed = {key for key in REVIEW_CHECK_IDS if review_checks[key] == "pass"}
    assert passed == set(SMOKE_REVIEW_CHECK_IDS)
    assert review_checks["provider_alerts_enabled"] == "fail"
    assert review_checks["backup_policy_confirmed"] == "pending"
    assert review_checks["operator_review_completed"] == "pending"


def test_smoke_round_trip_rejects_unexpected_fields(tmp_path: Path) -> None:
    path = tmp_path / "production-smoke.json"
    smoke = new_smoke(review=_review(), expected_commit=COMMIT)
    save_smoke(path, smoke)
    assert load_smoke(path) == smoke

    raw = path.read_text(encoding="utf-8").replace(
        '"schema_version": 1,',
        '"secret": "should-not-be-here",\n  "schema_version": 1,',
    )
    path.write_text(raw, encoding="utf-8")

    with pytest.raises(ValueError, match="unexpected or missing"):
        load_smoke(path)


def test_apply_review_cli_updates_bound_review(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    review_path = tmp_path / "production-review.json"
    smoke_path = tmp_path / "production-smoke.json"
    review = _review()
    smoke = new_smoke(review=review, expected_commit=COMMIT)
    _complete(smoke)
    save_review(review_path, review)
    save_smoke(smoke_path, smoke)
    monkeypatch.setattr(production_smoke, "_current_git_commit", lambda: COMMIT)

    assert (
        production_smoke.main(
            [
                "apply-review",
                "--input",
                str(smoke_path),
                "--review",
                str(review_path),
            ]
        )
        == 0
    )

    updated = load_review(review_path)
    passed = {key for key in REVIEW_CHECK_IDS if _checks(updated)[key] == "pass"}
    assert passed == set(SMOKE_REVIEW_CHECK_IDS)
