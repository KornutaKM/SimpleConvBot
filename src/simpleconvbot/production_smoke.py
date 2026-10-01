from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from simpleconvbot.image_operations import IMAGE_OPERATIONS
from simpleconvbot.media_operations import MEDIA_OPERATIONS
from simpleconvbot.pdf_operations import PDF_OPERATIONS
from simpleconvbot.production_review import (
    load_review,
    mark_review,
    review_summary,
    save_review,
)

SCHEMA_VERSION = 1
STATUSES = ("pass", "fail", "pending")
NON_ADVERTISED_OPERATION_IDS = frozenset({"image.compress", "video.compress"})
ADVERTISED_OPERATION_IDS = tuple(
    operation.operation_id
    for operation in (*IMAGE_OPERATIONS, *PDF_OPERATIONS, *MEDIA_OPERATIONS)
    if operation.operation_id not in NON_ADVERTISED_OPERATION_IDS
)
CHECK_IDS = (
    "navigation.ru_en",
    *ADVERTISED_OPERATION_IDS,
    "error.unsupported_input",
    "error.oversized_transport",
    "cleanup.after_success",
    "cleanup.after_failure",
    "runtime.controlled_redeploy_handoff",
    "runtime.healthy_after_smoke",
)
REVIEW_CHECK_IDS = (
    "production_smoke_completed",
    "cleanup_success_failure_verified",
    "oversized_transport_verified",
    "advertised_operations_observed",
)
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_IDENTITY = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def new_smoke(*, review: dict[str, object], expected_commit: str) -> dict[str, object]:
    review_summary(review, expected_commit=expected_commit)
    if review["commit_sha"] != expected_commit:
        raise ValueError("production review commit does not match current git HEAD")
    return {
        "schema_version": SCHEMA_VERSION,
        "commit_sha": review["commit_sha"],
        "provider": review["provider"],
        "deployment_id": review["deployment_id"],
        "runtime_identity": review["runtime_identity"],
        "updated_at": datetime.now(UTC).isoformat(),
        "checks": {check_id: "pending" for check_id in CHECK_IDS},
    }


def load_smoke(path: Path) -> dict[str, object]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("production smoke manifest must be a JSON object")
    smoke = cast(dict[str, object], raw)
    _validate_smoke(smoke)
    return smoke


def save_smoke(path: Path, smoke: dict[str, object]) -> None:
    _validate_smoke(smoke)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(smoke, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def mark_smoke(
    smoke: dict[str, object],
    *,
    check_id: str,
    status: str,
) -> dict[str, object]:
    _validate_smoke(smoke)
    if check_id not in CHECK_IDS:
        raise ValueError("unknown production smoke check")
    if status not in STATUSES:
        raise ValueError("status must be pass, fail, or pending")
    checks = cast(dict[str, object], smoke["checks"])
    checks[check_id] = status
    smoke["updated_at"] = datetime.now(UTC).isoformat()
    return smoke


def smoke_summary(smoke: dict[str, object], *, expected_commit: str) -> dict[str, object]:
    _validate_smoke(smoke)
    _validate_commit(expected_commit)
    checks = cast(dict[str, object], smoke["checks"])
    failed = [check_id for check_id in CHECK_IDS if checks[check_id] == "fail"]
    pending = [check_id for check_id in CHECK_IDS if checks[check_id] == "pending"]
    passed = sum(1 for check_id in CHECK_IDS if checks[check_id] == "pass")
    commit_matches = smoke["commit_sha"] == expected_commit
    smoke_ready = commit_matches and not failed and not pending
    return {
        "commit_matches": commit_matches,
        "commit_sha": smoke["commit_sha"],
        "provider": smoke["provider"],
        "deployment_id": smoke["deployment_id"],
        "runtime_identity": smoke["runtime_identity"],
        "advertised_operation_checks": len(ADVERTISED_OPERATION_IDS),
        "passed": passed,
        "failed": failed,
        "pending": pending,
        "status": "PASS" if smoke_ready else "PENDING",
        "smoke_ready": smoke_ready,
    }


def apply_smoke_to_review(
    smoke: dict[str, object],
    review: dict[str, object],
    *,
    expected_commit: str,
) -> None:
    smoke_state = smoke_summary(smoke, expected_commit=expected_commit)
    review_summary(review, expected_commit=expected_commit)
    if smoke_state["smoke_ready"] is not True:
        raise ValueError("production smoke is not ready")
    if review["commit_sha"] != expected_commit:
        raise ValueError("production review commit does not match current git HEAD")
    for field in ("commit_sha", "provider", "deployment_id", "runtime_identity"):
        if smoke[field] != review[field]:
            raise ValueError("production smoke binding does not match production review")
    for check_id in REVIEW_CHECK_IDS:
        mark_review(review, check_id=check_id, status="pass")


def _validate_smoke(smoke: dict[str, object]) -> None:
    expected_keys = {
        "schema_version",
        "commit_sha",
        "provider",
        "deployment_id",
        "runtime_identity",
        "updated_at",
        "checks",
    }
    if set(smoke) != expected_keys:
        raise ValueError("production smoke contains unexpected or missing fields")
    if smoke["schema_version"] != SCHEMA_VERSION:
        raise ValueError("unsupported production smoke schema version")

    commit = smoke["commit_sha"]
    if not isinstance(commit, str):
        raise ValueError("commit_sha must be a string")
    _validate_commit(commit)

    provider = smoke["provider"]
    if provider != "railway":
        raise ValueError("invalid production provider")

    for field in ("deployment_id", "runtime_identity"):
        value = smoke[field]
        if not isinstance(value, str):
            raise ValueError(f"{field} must be a string")
        _validate_identity(field, value)

    if not isinstance(smoke["updated_at"], str):
        raise ValueError("updated_at must be a string")

    checks = smoke["checks"]
    if not isinstance(checks, dict) or set(checks) != set(CHECK_IDS):
        raise ValueError("production smoke checks are incomplete")
    for status in cast(dict[str, object], checks).values():
        if status not in STATUSES:
            raise ValueError("invalid production smoke status")


def _validate_commit(value: str) -> None:
    if _COMMIT.fullmatch(value) is None:
        raise ValueError("commit_sha must be a full lowercase 40-character SHA")


def _validate_identity(name: str, value: str) -> None:
    if _IDENTITY.fullmatch(value) is None:
        raise ValueError(f"{name} must be a bounded machine identifier")


def _current_git_commit() -> str:
    from simpleconvbot.production_review import current_git_commit

    return current_git_commit()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Record comprehensive production smoke evidence.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init")
    init.add_argument("--output", type=Path, required=True)
    init.add_argument("--review", type=Path, required=True)

    mark = subparsers.add_parser("mark")
    mark.add_argument("--input", type=Path, required=True)
    mark.add_argument("--check", choices=CHECK_IDS, required=True)
    mark.add_argument("--status", choices=STATUSES, required=True)

    show = subparsers.add_parser("show")
    show.add_argument("--input", type=Path, required=True)
    show.add_argument("--require-ready", action="store_true")

    apply_review = subparsers.add_parser("apply-review")
    apply_review.add_argument("--input", type=Path, required=True)
    apply_review.add_argument("--review", type=Path, required=True)

    args = parser.parse_args(argv)
    commit = _current_git_commit()

    if args.command == "init":
        review = load_review(args.review)
        smoke = new_smoke(review=review, expected_commit=commit)
        save_smoke(args.output, smoke)
    else:
        smoke = load_smoke(args.input)
        if args.command == "mark":
            if smoke["commit_sha"] != commit:
                raise ValueError("production smoke commit does not match current git HEAD")
            mark_smoke(smoke, check_id=args.check, status=args.status)
            save_smoke(args.input, smoke)
        elif args.command == "apply-review":
            review = load_review(args.review)
            apply_smoke_to_review(smoke, review, expected_commit=commit)
            save_review(args.review, review)

    summary = smoke_summary(smoke, expected_commit=commit)
    json.dump(summary, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    if args.command == "show" and args.require_ready and not summary["smoke_ready"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
