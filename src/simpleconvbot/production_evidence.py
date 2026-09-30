from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_MACHINE_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


@dataclass(slots=True)
class _Evidence:
    identities: list[dict[str, object]] = field(default_factory=list)
    lease_acquired: int = 0
    runtime_ready: int = 0
    polling_start: int = 0
    recovery_summaries: int = 0
    retention_policy: int = 0
    cleanup_success: int = 0
    production_health_ready: int = 0
    polling_conflicts: int = 0

    def consume_line(self, line: str) -> None:
        if "TelegramConflictError" in line or "terminated by other getUpdates request" in line:
            self.polling_conflicts += 1

        payload = _parse_payload(line)
        if payload is None:
            return
        event = payload.get("event")
        if event == "runtime_identity":
            self.identities.append(payload)
        elif event == "runtime_lease" and payload.get("outcome") == "acquired":
            self.lease_acquired += 1
        elif event == "runtime_ready":
            self.runtime_ready += 1
        elif event == "polling_start":
            self.polling_start += 1
        elif event == "recovery_summary":
            self.recovery_summaries += 1
        elif event == "retention_policy":
            self.retention_policy += 1
        elif event == "cleanup" and payload.get("outcome") == "success":
            self.cleanup_success += 1
        elif event == "admin_diagnostic":
            health = payload.get("health")
            if (
                payload.get("environment") == "production"
                and isinstance(health, dict)
                and cast(dict[str, Any], health).get("ready") is True
            ):
                self.production_health_ready += 1


def summarize_lines(
    lines: Iterable[str],
    *,
    expected_commit: str,
    expected_deployment_id: str,
) -> dict[str, object]:
    _validate_commit(expected_commit)
    _validate_machine("expected_deployment_id", expected_deployment_id)
    evidence = _Evidence()
    for line in lines:
        evidence.consume_line(line)

    identity_matches = sum(
        1
        for item in evidence.identities
        if item.get("provider") == "railway"
        and item.get("git_commit") == expected_commit
        and item.get("deployment_id") == expected_deployment_id
    )
    checks = {
        "deployment_identity_matches": _gate(identity_matches > 0, identity_matches),
        "singleton_lease_acquired": _gate(evidence.lease_acquired > 0, evidence.lease_acquired),
        "startup_recovery_observed": _gate(
            evidence.recovery_summaries > 0,
            evidence.recovery_summaries,
        ),
        "retention_policy_observed": _gate(
            evidence.retention_policy > 0,
            evidence.retention_policy,
        ),
        "initial_cleanup_succeeded": _gate(
            evidence.cleanup_success > 0,
            evidence.cleanup_success,
        ),
        "production_dependencies_ready": _gate(
            evidence.production_health_ready > 0,
            evidence.production_health_ready,
        ),
        "runtime_ready_observed": _gate(evidence.runtime_ready > 0, evidence.runtime_ready),
        "polling_started": _gate(evidence.polling_start > 0, evidence.polling_start),
        "polling_conflict_free": _gate(
            evidence.polling_start > 0 and evidence.polling_conflicts == 0,
            evidence.polling_conflicts,
        ),
    }
    ready = all(check["status"] == "PASS" for check in checks.values())
    return {
        "expected_commit": expected_commit,
        "expected_deployment_id": expected_deployment_id,
        "identity_events": len(evidence.identities),
        "polling_conflicts": evidence.polling_conflicts,
        "checks": checks,
        "machine_production_ready": ready,
    }


def _parse_payload(line: str) -> dict[str, object] | None:
    decoder = json.JSONDecoder()
    offset = line.find("{")
    while offset >= 0:
        try:
            value, _ = decoder.raw_decode(line[offset:])
        except json.JSONDecodeError:
            offset = line.find("{", offset + 1)
            continue
        if isinstance(value, dict):
            payload = cast(dict[str, Any], value)
            if isinstance(payload.get("event"), str):
                return cast(dict[str, object], payload)
        offset = line.find("{", offset + 1)
    return None


def _gate(passed: bool, observed: int) -> dict[str, object]:
    return {"status": "PASS" if passed else "PENDING", "observed": observed}


def _validate_commit(value: str) -> None:
    if _COMMIT.fullmatch(value) is None:
        raise ValueError("expected_commit must be a full lowercase commit SHA")


def _validate_machine(name: str, value: str) -> None:
    if _MACHINE_ID.fullmatch(value) is None:
        raise ValueError(f"{name} must be a bounded machine identifier")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Summarize privacy-safe production runtime evidence."
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--expected-deployment-id", required=True)
    parser.add_argument("--require-machine-ready", action="store_true")
    args = parser.parse_args(argv)

    with args.input.open("r", encoding="utf-8", errors="replace") as stream:
        summary = summarize_lines(
            stream,
            expected_commit=args.expected_commit,
            expected_deployment_id=args.expected_deployment_id,
        )

    json.dump(summary, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    if args.require_machine_ready and summary["machine_production_ready"] is not True:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
