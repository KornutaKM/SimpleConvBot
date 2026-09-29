from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

from simpleconvbot.alpha_manual_review import (
    CHECK_IDS,
    load_review,
    mark_review,
    new_review,
    review_summary,
    save_review,
)

COMMIT = "1" * 40
OTHER_COMMIT = "2" * 40


def _mapping(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    return cast(dict[str, object], value)


def test_manual_review_starts_pending_and_is_commit_bound() -> None:
    review = new_review(
        commit_sha=COMMIT,
        execution_mode="compose",
        runtime_identity="sha256:abcdef123456",
    )

    summary = review_summary(review, expected_commit=COMMIT)

    assert summary["commit_matches"] is True
    assert summary["manual_review_ready"] is False
    locales = _mapping(summary["locales"])
    for locale in ("ru", "en"):
        locale_summary = _mapping(locales[locale])
        assert locale_summary["status"] == "PENDING"
        assert locale_summary["passed"] == 0
        assert locale_summary["failed"] == []
        assert locale_summary["pending"] == list(CHECK_IDS)


def test_manual_review_requires_both_locales_and_exact_commit() -> None:
    review = new_review(
        commit_sha=COMMIT,
        execution_mode="host-python",
        runtime_identity=COMMIT,
    )
    mark_review(review, locale="ru", check_id="all", status="pass")

    one_locale = review_summary(review, expected_commit=COMMIT)
    assert one_locale["manual_review_ready"] is False
    assert _mapping(_mapping(one_locale["locales"])["ru"])["status"] == "PASS"
    assert _mapping(_mapping(one_locale["locales"])["en"])["status"] == "PENDING"

    mark_review(review, locale="en", check_id="all", status="pass")
    complete = review_summary(review, expected_commit=COMMIT)
    assert complete["manual_review_ready"] is True

    stale = review_summary(review, expected_commit=OTHER_COMMIT)
    assert stale["commit_matches"] is False
    assert stale["manual_review_ready"] is False


def test_manual_review_round_trip_rejects_extra_private_fields(tmp_path: Path) -> None:
    path = tmp_path / "alpha-review.json"
    review = new_review(
        commit_sha=COMMIT,
        execution_mode="compose",
        runtime_identity="sha256:deadbeef",
    )
    save_review(path, review)

    assert load_review(path) == review

    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["filename"] = "private.pdf"
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ValueError, match="unexpected or missing"):
        load_review(path)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("commit_sha", "abc"),
        ("execution_mode", "remote"),
        ("runtime_identity", "contains spaces"),
    ],
)
def test_manual_review_identity_is_bounded(field: str, value: str) -> None:
    kwargs = {
        "commit_sha": COMMIT,
        "execution_mode": "compose",
        "runtime_identity": "sha256:abcdef",
    }
    kwargs[field] = value
    with pytest.raises(ValueError):
        new_review(**kwargs)
