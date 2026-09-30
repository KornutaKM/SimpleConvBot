from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

import simpleconvbot.production_review as production_review
from simpleconvbot.production_review import (
    CHECK_IDS,
    load_review,
    mark_review,
    new_review,
    review_summary,
    save_review,
)

COMMIT = "1" * 40
OTHER_COMMIT = "2" * 40


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
