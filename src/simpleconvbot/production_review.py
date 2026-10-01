from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from simpleconvbot.production_evidence import summarize_lines

SCHEMA_VERSION = 2
PROVIDERS = ("railway",)
CHECK_IDS = (
    "backup_policy_confirmed",
    "railway_project_configured",
    "postgres_redis_provisioned",
    "production_secrets_installed",
    "exact_revision_deployed",
    "singleton_polling_confirmed",
    "startup_health_confirmed",
    "provider_alerts_enabled",
    "botfather_profile_configured",
    "production_smoke_completed",
    "cleanup_success_failure_verified",
    "oversized_transport_verified",
    "rollback_drill_approved",
    "no_open_security_gate",
    "no_unexplained_failure_class",
    "privacy_matches_deployment",
    "advertised_operations_observed",
    "operator_review_completed",
)
STATUSES = ("pass", "fail", "pending")
MACHINE_IMPORT_CHECK_IDS = (
    "exact_revision_deployed",
    "singleton_polling_confirmed",
    "startup_health_confirmed",
)
SMOKE_IMPORT_CHECK_IDS = (
    "production_smoke_completed",
    "cleanup_success_failure_verified",
    "oversized_transport_verified",
    "advertised_operations_observed",
)
HUMAN_ATTESTATION_CHECK_IDS = tuple(
    check_id
    for check_id in CHECK_IDS
    if check_id not in {*MACHINE_IMPORT_CHECK_IDS, *SMOKE_IMPORT_CHECK_IDS}
)
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_IDENTITY = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_EVIDENCE_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/#@+\-]{0,255}$")


def current_git_commit() -> str:
    result = subprocess.run(
        ("git", "rev-parse", "HEAD"),
        check=True,
        capture_output=True,
        text=True,
    )
    commit = result.stdout.strip()
    _validate_commit(commit)
    return commit


def new_review(
    *,
    commit_sha: str,
    provider: str,
    deployment_id: str,
    runtime_identity: str,
) -> dict[str, object]:
    _validate_commit(commit_sha)
    if provider not in PROVIDERS:
        raise ValueError("unsupported production provider")
    _validate_identity("deployment_id", deployment_id)
    _validate_identity("runtime_identity", runtime_identity)
    return {
        "schema_version": SCHEMA_VERSION,
        "commit_sha": commit_sha,
        "provider": provider,
        "deployment_id": deployment_id,
        "runtime_identity": runtime_identity,
        "updated_at": datetime.now(UTC).isoformat(),
        "checks": {check_id: "pending" for check_id in CHECK_IDS},
        "evidence_refs": {check_id: None for check_id in HUMAN_ATTESTATION_CHECK_IDS},
    }


def load_review(path: Path) -> dict[str, object]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("production review must be a JSON object")
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
    check_id: str,
    status: str,
    evidence_ref: str | None = None,
) -> dict[str, object]:
    _validate_review(review)
    if check_id not in CHECK_IDS:
        raise ValueError("unknown production review check")
    if status not in STATUSES:
        raise ValueError("status must be pass, fail, or pending")

    if status == "pass":
        if check_id in MACHINE_IMPORT_CHECK_IDS:
            raise ValueError("machine-owned check can only pass through import-machine")
        if check_id in SMOKE_IMPORT_CHECK_IDS:
            raise ValueError(
                "smoke-owned check can only pass through production_smoke apply-review"
            )
        if evidence_ref is None:
            raise ValueError("human-owned PASS requires --evidence-ref")
        _validate_evidence_ref(evidence_ref)
    elif evidence_ref is not None:
        raise ValueError("--evidence-ref is only valid with PASS")

    checks = cast(dict[str, object], review["checks"])
    checks[check_id] = status
    if check_id in HUMAN_ATTESTATION_CHECK_IDS:
        refs = cast(dict[str, object], review["evidence_refs"])
        refs[check_id] = evidence_ref if status == "pass" else None
    review["updated_at"] = datetime.now(UTC).isoformat()
    return review


def mark_owned_review_pass(
    review: dict[str, object],
    *,
    check_id: str,
    owner: str,
) -> dict[str, object]:
    _validate_review(review)
    owned = {
        "machine": MACHINE_IMPORT_CHECK_IDS,
        "smoke": SMOKE_IMPORT_CHECK_IDS,
    }.get(owner)
    if owned is None:
        raise ValueError("unknown production review evidence owner")
    if check_id not in owned:
        raise ValueError("production review check does not belong to evidence owner")
    checks = cast(dict[str, object], review["checks"])
    checks[check_id] = "pass"
    review["updated_at"] = datetime.now(UTC).isoformat()
    return review


def import_machine_evidence(
    review: dict[str, object],
    *,
    evidence_lines: list[str],
    expected_commit: str,
) -> dict[str, object]:
    _validate_review(review)
    _validate_commit(expected_commit)
    if review["commit_sha"] != expected_commit:
        raise ValueError("production review commit does not match current git HEAD")

    deployment_id = review["deployment_id"]
    if not isinstance(deployment_id, str):
        raise ValueError("deployment_id must be a string")

    machine_summary = summarize_lines(
        evidence_lines,
        expected_commit=expected_commit,
        expected_deployment_id=deployment_id,
    )
    if machine_summary["machine_production_ready"] is not True:
        raise ValueError("production machine evidence is not ready")

    for check_id in MACHINE_IMPORT_CHECK_IDS:
        mark_owned_review_pass(review, check_id=check_id, owner="machine")
    return machine_summary


def review_summary(review: dict[str, object], *, expected_commit: str) -> dict[str, object]:
    _validate_review(review)
    _validate_commit(expected_commit)
    checks = cast(dict[str, object], review["checks"])
    failed = [check_id for check_id in CHECK_IDS if checks[check_id] == "fail"]
    pending = [check_id for check_id in CHECK_IDS if checks[check_id] == "pending"]
    passed = sum(1 for check_id in CHECK_IDS if checks[check_id] == "pass")
    refs = cast(dict[str, object], review["evidence_refs"])
    human_evidence_refs = [
        check_id for check_id in HUMAN_ATTESTATION_CHECK_IDS if refs[check_id] is not None
    ]
    commit_matches = review["commit_sha"] == expected_commit
    release_ready = commit_matches and not failed and not pending
    return {
        "commit_matches": commit_matches,
        "commit_sha": review["commit_sha"],
        "provider": review["provider"],
        "deployment_id": review["deployment_id"],
        "runtime_identity": review["runtime_identity"],
        "passed": passed,
        "human_evidence_refs": human_evidence_refs,
        "failed": failed,
        "pending": pending,
        "status": "PASS" if release_ready else "PENDING",
        "release_ready": release_ready,
    }


def _validate_review(review: dict[str, object]) -> None:
    if review.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported production review schema version")
    expected_keys = {
        "schema_version",
        "commit_sha",
        "provider",
        "deployment_id",
        "runtime_identity",
        "updated_at",
        "checks",
        "evidence_refs",
    }
    if set(review) != expected_keys:
        raise ValueError("production review contains unexpected or missing fields")

    commit = review["commit_sha"]
    if not isinstance(commit, str):
        raise ValueError("commit_sha must be a string")
    _validate_commit(commit)

    if review["provider"] not in PROVIDERS:
        raise ValueError("invalid production provider")

    deployment_id = review["deployment_id"]
    if not isinstance(deployment_id, str):
        raise ValueError("deployment_id must be a string")
    _validate_identity("deployment_id", deployment_id)

    runtime_identity = review["runtime_identity"]
    if not isinstance(runtime_identity, str):
        raise ValueError("runtime_identity must be a string")
    _validate_identity("runtime_identity", runtime_identity)

    if not isinstance(review["updated_at"], str):
        raise ValueError("updated_at must be a string")

    checks = review["checks"]
    if not isinstance(checks, dict) or set(checks) != set(CHECK_IDS):
        raise ValueError("production review checks are incomplete")
    for status in cast(dict[str, object], checks).values():
        if status not in STATUSES:
            raise ValueError("invalid production review status")

    refs = review["evidence_refs"]
    if not isinstance(refs, dict) or set(refs) != set(HUMAN_ATTESTATION_CHECK_IDS):
        raise ValueError("production review evidence refs are incomplete")
    for check_id, value in cast(dict[str, object], refs).items():
        if value is not None:
            if not isinstance(value, str):
                raise ValueError("production review evidence ref must be a string or null")
            _validate_evidence_ref(value)
        status = cast(dict[str, object], checks)[check_id]
        if status == "pass" and value is None:
            raise ValueError("human-owned PASS is missing evidence ref")
        if status != "pass" and value is not None:
            raise ValueError("non-PASS human check cannot retain evidence ref")


def _validate_commit(commit_sha: str) -> None:
    if _COMMIT.fullmatch(commit_sha) is None:
        raise ValueError("commit_sha must be a full lowercase 40-character SHA")


def _validate_identity(name: str, value: str) -> None:
    if _IDENTITY.fullmatch(value) is None:
        raise ValueError(f"{name} must be a bounded machine identifier")


def _validate_evidence_ref(value: str) -> None:
    if _EVIDENCE_REF.fullmatch(value) is None:
        raise ValueError("evidence_ref must be a bounded non-secret reference")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Record exact-deployment production release evidence."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init")
    init.add_argument("--output", type=Path, required=True)
    init.add_argument("--provider", choices=PROVIDERS, required=True)
    init.add_argument("--deployment-id", required=True)
    init.add_argument("--runtime-id", required=True)

    mark = subparsers.add_parser("mark")
    mark.add_argument("--input", type=Path, required=True)
    mark.add_argument("--check", choices=CHECK_IDS, required=True)
    mark.add_argument("--status", choices=STATUSES, required=True)
    mark.add_argument("--evidence-ref")

    import_machine = subparsers.add_parser("import-machine")
    import_machine.add_argument("--input", type=Path, required=True)
    import_machine.add_argument("--evidence", type=Path, required=True)

    show = subparsers.add_parser("show")
    show.add_argument("--input", type=Path, required=True)
    show.add_argument("--require-ready", action="store_true")

    args = parser.parse_args(argv)

    if args.command == "init":
        commit = current_git_commit()
        review = new_review(
            commit_sha=commit,
            provider=args.provider,
            deployment_id=args.deployment_id,
            runtime_identity=args.runtime_id,
        )
        save_review(args.output, review)
        summary = review_summary(review, expected_commit=commit)
    else:
        review = load_review(args.input)
        current_commit = current_git_commit()
        if args.command == "mark":
            if review["commit_sha"] != current_commit:
                raise ValueError("production review commit does not match current git HEAD")
            mark_review(
                review,
                check_id=args.check,
                status=args.status,
                evidence_ref=args.evidence_ref,
            )
            save_review(args.input, review)
        elif args.command == "import-machine":
            with args.evidence.open("r", encoding="utf-8", errors="replace") as stream:
                import_machine_evidence(
                    review,
                    evidence_lines=list(stream),
                    expected_commit=current_commit,
                )
            save_review(args.input, review)
        summary = review_summary(review, expected_commit=current_commit)

    json.dump(summary, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")

    if args.command == "show" and args.require_ready and not summary["release_ready"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
