from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

SCHEMA_VERSION = 1
LOCALES = ("ru", "en")
CHECK_IDS = (
    "home_and_tools_navigation",
    "image_actions",
    "pdf_actions",
    "audio_actions",
    "video_actions",
    "images_to_pdf_collection",
    "pdf_merge_collection",
    "unsupported_input_error",
    "oversized_input_error",
    "generic_failure_error",
    "settings_and_back_navigation",
)
STATUSES = ("pass", "fail", "pending")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_RUNTIME_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def current_git_commit() -> str:
    result = subprocess.run(
        ("git", "rev-parse", "HEAD"),
        check=True,
        capture_output=True,
        text=True,
    )
    commit = result.stdout.strip()
    if _COMMIT.fullmatch(commit) is None:
        raise ValueError("git HEAD is not a full 40-character commit SHA")
    return commit


def new_review(*, commit_sha: str, execution_mode: str, runtime_identity: str) -> dict[str, object]:
    _validate_commit(commit_sha)
    if execution_mode not in {"compose", "host-python"}:
        raise ValueError("execution_mode must be compose or host-python")
    if _RUNTIME_ID.fullmatch(runtime_identity) is None:
        raise ValueError("runtime_identity must be a bounded machine identifier")
    return {
        "schema_version": SCHEMA_VERSION,
        "commit_sha": commit_sha,
        "execution_mode": execution_mode,
        "runtime_identity": runtime_identity,
        "updated_at": datetime.now(UTC).isoformat(),
        "locales": {
            locale: {check_id: "pending" for check_id in CHECK_IDS}
            for locale in LOCALES
        },
    }


def load_review(path: Path) -> dict[str, object]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("manual review must be a JSON object")
    review = cast(dict[str, object], raw)
    _validate_review(review)
    return review


def save_review(path: Path, review: dict[str, object]) -> None:
    _validate_review(review)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(review, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def mark_review(
    review: dict[str, object],
    *,
    locale: str,
    check_id: str,
    status: str,
) -> dict[str, object]:
    _validate_review(review)
    if locale not in LOCALES:
        raise ValueError("unsupported locale")
    if check_id != "all" and check_id not in CHECK_IDS:
        raise ValueError("unknown manual review check")
    if status not in STATUSES:
        raise ValueError("status must be pass, fail, or pending")

    locales = cast(dict[str, object], review["locales"])
    checks = cast(dict[str, object], locales[locale])
    targets = CHECK_IDS if check_id == "all" else (check_id,)
    for target in targets:
        checks[target] = status
    review["updated_at"] = datetime.now(UTC).isoformat()
    return review


def review_summary(review: dict[str, object], *, expected_commit: str) -> dict[str, object]:
    _validate_review(review)
    _validate_commit(expected_commit)
    commit_matches = review["commit_sha"] == expected_commit
    locales = cast(dict[str, object], review["locales"])
    locale_summary: dict[str, object] = {}
    all_pass = commit_matches

    for locale in LOCALES:
        checks = cast(dict[str, object], locales[locale])
        failed = [check_id for check_id in CHECK_IDS if checks[check_id] == "fail"]
        pending = [check_id for check_id in CHECK_IDS if checks[check_id] == "pending"]
        passed = sum(1 for check_id in CHECK_IDS if checks[check_id] == "pass")
        ready = not failed and not pending
        all_pass = all_pass and ready
        locale_summary[locale] = {
            "status": "PASS" if ready else "PENDING",
            "passed": passed,
            "failed": failed,
            "pending": pending,
        }

    return {
        "commit_matches": commit_matches,
        "commit_sha": review["commit_sha"],
        "execution_mode": review["execution_mode"],
        "runtime_identity": review["runtime_identity"],
        "locales": locale_summary,
        "manual_review_ready": all_pass,
    }


def _validate_review(review: dict[str, object]) -> None:
    expected_keys = {
        "schema_version",
        "commit_sha",
        "execution_mode",
        "runtime_identity",
        "updated_at",
        "locales",
    }
    if set(review) != expected_keys:
        raise ValueError("manual review contains unexpected or missing fields")
    if review["schema_version"] != SCHEMA_VERSION:
        raise ValueError("unsupported manual review schema version")
    commit = review["commit_sha"]
    if not isinstance(commit, str):
        raise ValueError("commit_sha must be a string")
    _validate_commit(commit)
    if review["execution_mode"] not in {"compose", "host-python"}:
        raise ValueError("invalid execution_mode")
    runtime_identity = review["runtime_identity"]
    if not isinstance(runtime_identity, str) or _RUNTIME_ID.fullmatch(runtime_identity) is None:
        raise ValueError("invalid runtime_identity")
    updated_at = review["updated_at"]
    if not isinstance(updated_at, str):
        raise ValueError("updated_at must be a string")

    locales = review["locales"]
    if not isinstance(locales, dict) or set(locales) != set(LOCALES):
        raise ValueError("manual review must contain ru and en locales")
    typed_locales = cast(dict[str, Any], locales)
    for locale in LOCALES:
        checks = typed_locales[locale]
        if not isinstance(checks, dict) or set(checks) != set(CHECK_IDS):
            raise ValueError(f"manual review checks are incomplete for {locale}")
        for status in cast(dict[str, object], checks).values():
            if status not in STATUSES:
                raise ValueError("invalid manual review status")


def _validate_commit(commit_sha: str) -> None:
    if _COMMIT.fullmatch(commit_sha) is None:
        raise ValueError("commit_sha must be a full lowercase 40-character SHA")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Record bounded local RU/EN alpha UX review.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init")
    init.add_argument("--output", type=Path, required=True)
    init.add_argument("--execution-mode", choices=("compose", "host-python"), required=True)
    init.add_argument("--runtime-id", required=True)

    mark = subparsers.add_parser("mark")
    mark.add_argument("--input", type=Path, required=True)
    mark.add_argument("--locale", choices=LOCALES, required=True)
    mark.add_argument("--check", choices=(*CHECK_IDS, "all"), required=True)
    mark.add_argument("--status", choices=STATUSES, required=True)

    show = subparsers.add_parser("show")
    show.add_argument("--input", type=Path, required=True)

    args = parser.parse_args(argv)
    if args.command == "init":
        review = new_review(
            commit_sha=current_git_commit(),
            execution_mode=args.execution_mode,
            runtime_identity=args.runtime_id,
        )
        save_review(args.output, review)
        json.dump(
            review_summary(review, expected_commit=cast(str, review["commit_sha"])),
            sys.stdout,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        sys.stdout.write("\n")
        return 0

    review = load_review(args.input)
    current_commit = current_git_commit()
    if args.command == "mark":
        if review["commit_sha"] != current_commit:
            raise ValueError("manual review commit does not match current git HEAD")
        mark_review(review, locale=args.locale, check_id=args.check, status=args.status)
        save_review(args.input, review)

    summary = review_summary(review, expected_commit=current_commit)
    json.dump(summary, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
