from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

_REQUIRED_E2E_STAGES = frozenset({"validation", "queue", "worker", "upload", "cleanup"})


@dataclass(slots=True)
class _StageCounter:
    success: int = 0
    failure: int = 0

    def record(self, outcome: str) -> None:
        if outcome == "success":
            self.success += 1
        elif outcome == "failure":
            self.failure += 1

    def to_payload(self) -> dict[str, int]:
        return {"success": self.success, "failure": self.failure}


@dataclass(slots=True)
class _RunAccumulator:
    stage_outcomes: dict[str, set[str]] = field(default_factory=dict)
    validation_count: int | None = None

    def record(self, stage: str, outcome: str, count: int | None) -> None:
        self.stage_outcomes.setdefault(stage, set()).add(outcome)
        if stage == "validation" and count is not None:
            self.validation_count = count

    def is_e2e_success(self) -> bool:
        for stage in _REQUIRED_E2E_STAGES:
            outcomes = self.stage_outcomes.get(stage, set())
            if "success" not in outcomes or "failure" in outcomes:
                return False
        return True

    def has_failed_stage_with_successful_cleanup(self) -> bool:
        cleanup = self.stage_outcomes.get("cleanup", set())
        if "success" not in cleanup or "failure" in cleanup:
            return False
        return any(
            "failure" in outcomes
            for stage, outcomes in self.stage_outcomes.items()
            if stage != "cleanup"
        )


@dataclass(slots=True)
class _OperationAccumulator:
    stages: dict[str, _StageCounter] = field(default_factory=dict)
    runs: dict[str, _RunAccumulator] = field(default_factory=dict)

    def record(
        self,
        *,
        correlation_id: str | None,
        stage: str,
        outcome: str,
        count: int | None,
    ) -> None:
        self.stages.setdefault(stage, _StageCounter()).record(outcome)
        if correlation_id is not None:
            self.runs.setdefault(correlation_id, _RunAccumulator()).record(stage, outcome, count)

    def e2e_success_count(self) -> int:
        return sum(1 for run in self.runs.values() if run.is_e2e_success())

    def multi_file_e2e_success_count(self) -> int:
        return sum(
            1
            for run in self.runs.values()
            if run.is_e2e_success()
            and run.validation_count is not None
            and run.validation_count >= 2
        )

    def failed_run_cleanup_success_count(self) -> int:
        return sum(
            1
            for run in self.runs.values()
            if run.has_failed_stage_with_successful_cleanup()
        )

    def to_payload(self) -> dict[str, object]:
        e2e_success = self.e2e_success_count()
        multi_file_e2e_success = self.multi_file_e2e_success_count()
        validation_counts: list[int] = []
        for run in self.runs.values():
            if run.validation_count is not None:
                validation_counts.append(run.validation_count)

        return {
            "runs": {
                "observed": len(self.runs),
                "e2e_success": e2e_success,
                "multi_file_e2e_success": multi_file_e2e_success,
            },
            "stages": {
                stage: counter.to_payload() for stage, counter in sorted(self.stages.items())
            },
            "validation_input_counts": sorted(validation_counts),
        }


@dataclass(slots=True)
class _EvidenceAccumulator:
    operations: dict[str, _OperationAccumulator] = field(default_factory=dict)
    duplicate_events: int = 0
    duplicate_count: int = 0
    input_rejection_events: int = 0
    input_rejections_by_error: dict[str, int] = field(default_factory=dict)
    recovery_summaries: int = 0
    recovery_clean_summaries: int = 0
    recovery_actions_total: int = 0
    recovery_inflight_items: int = 0
    recovery_interrupted_failed: int = 0
    recovery_queued_reenqueued: int = 0
    cleanup_events: int = 0
    cleanup_success: int = 0
    cleanup_failure: int = 0
    cleanup_deleted_total: int = 0
    retention_policy_events: int = 0
    latest_retention_policy: dict[str, int] | None = None
    latest_admin_diagnostic: dict[str, object] | None = None

    def consume(self, payload: dict[str, object]) -> None:
        event = _string(payload.get("event"))
        if event == "operation_stage":
            self._consume_operation(payload)
        elif event == "update_deduplicated":
            self.duplicate_events += 1
            self.duplicate_count += _integer(payload.get("count")) or 0
        elif event == "input_rejected":
            error_code = _string(payload.get("error_code"))
            if error_code is not None:
                self.input_rejection_events += 1
                count = _integer(payload.get("count")) or 1
                self.input_rejections_by_error[error_code] = (
                    self.input_rejections_by_error.get(error_code, 0) + count
                )
        elif event == "recovery":
            self._consume_recovery(payload)
        elif event == "recovery_summary":
            count = _integer(payload.get("count")) or 0
            self.recovery_summaries += 1
            self.recovery_actions_total += count
            if count == 0:
                self.recovery_clean_summaries += 1
        elif event == "cleanup":
            self._consume_cleanup(payload)
        elif event == "retention_policy":
            ttl_seconds = _integer(payload.get("ttl_seconds"))
            interval_seconds = _integer(payload.get("interval_seconds"))
            if (
                ttl_seconds is not None
                and ttl_seconds > 0
                and interval_seconds is not None
                and interval_seconds > 0
            ):
                self.retention_policy_events += 1
                self.latest_retention_policy = {
                    "ttl_seconds": ttl_seconds,
                    "sweep_interval_seconds": interval_seconds,
                    "max_cleanup_delay_seconds": ttl_seconds + interval_seconds,
                }
        elif event == "admin_diagnostic":
            self.latest_admin_diagnostic = _admin_summary(payload)

    def _consume_operation(self, payload: dict[str, object]) -> None:
        operation_id = _string(payload.get("operation_id"))
        stage = _string(payload.get("stage"))
        outcome = _string(payload.get("outcome"))
        if operation_id is None or stage is None or outcome not in {"success", "failure"}:
            return
        correlation_id = _string(payload.get("correlation_id"))
        count = _integer(payload.get("count"))
        self.operations.setdefault(operation_id, _OperationAccumulator()).record(
            correlation_id=correlation_id,
            stage=stage,
            outcome=outcome,
            count=count,
        )

    def _consume_recovery(self, payload: dict[str, object]) -> None:
        outcome = _string(payload.get("outcome"))
        error_code = _string(payload.get("error_code"))
        operation_id = _string(payload.get("operation_id"))
        count = _integer(payload.get("count"))

        if outcome == "failure" and error_code == "restart_interrupted":
            self.recovery_interrupted_failed += count or 1
            return
        if outcome != "success":
            return
        if operation_id is not None and count is None:
            self.recovery_queued_reenqueued += 1
            return
        if operation_id is None and count is not None and count > 0:
            self.recovery_inflight_items += count

    def _consume_cleanup(self, payload: dict[str, object]) -> None:
        outcome = _string(payload.get("outcome"))
        count = _integer(payload.get("count")) or 0
        self.cleanup_events += 1
        self.cleanup_deleted_total += count
        if outcome == "success":
            self.cleanup_success += 1
        elif outcome == "failure":
            self.cleanup_failure += 1

    def to_payload(self) -> dict[str, object]:
        operations = {
            operation_id: accumulator.to_payload()
            for operation_id, accumulator in sorted(self.operations.items())
        }
        payload: dict[str, object] = {
            "operations": operations,
            "duplicate_updates": {
                "events": self.duplicate_events,
                "dropped_total": self.duplicate_count,
            },
            "input_rejections": {
                "events": self.input_rejection_events,
                "by_error_code": dict(sorted(self.input_rejections_by_error.items())),
            },
            "recovery": {
                "summary_events": self.recovery_summaries,
                "clean_summary_events": self.recovery_clean_summaries,
                "actions_total": self.recovery_actions_total,
                "inflight_queue_items": self.recovery_inflight_items,
                "interrupted_failed": self.recovery_interrupted_failed,
                "queued_reenqueued": self.recovery_queued_reenqueued,
            },
            "retention_cleanup": {
                "events": self.cleanup_events,
                "success": self.cleanup_success,
                "failure": self.cleanup_failure,
                "deleted_total": self.cleanup_deleted_total,
            },
            "retention_policy": {
                "events": self.retention_policy_events,
                "latest": self.latest_retention_policy,
            },
            "latest_admin_diagnostic": self.latest_admin_diagnostic,
        }
        payload["runtime_gates"] = self._runtime_gates()
        return payload

    def _runtime_gates(self) -> dict[str, object]:
        image_collection = self._multi_file_success("pdf.from_images")
        pdf_merge = self._multi_file_success("pdf.merge")
        successful_runs = sum(
            operation.e2e_success_count() for operation in self.operations.values()
        )
        failed_cleanup_runs = sum(
            operation.failed_run_cleanup_success_count()
            for operation in self.operations.values()
        )
        unsupported_count = self.input_rejections_by_error.get("unsupported_document", 0)
        oversized_count = self.input_rejections_by_error.get(
            "telegram_input_too_large", 0
        )
        health_ready = False
        if self.latest_admin_diagnostic is not None:
            health_ready = self.latest_admin_diagnostic.get("health_ready") is True

        checks = {
            "images_to_pdf_multifile": _gate(image_collection > 0, image_collection),
            "pdf_merge_multifile": _gate(pdf_merge > 0, pdf_merge),
            "duplicate_update_suppression": _gate(
                self.duplicate_count > 0, self.duplicate_count
            ),
            "unsupported_input_rejection": _gate(
                unsupported_count > 0, unsupported_count
            ),
            "oversized_input_rejection": _gate(oversized_count > 0, oversized_count),
            "interrupted_restart_fail_closed": _gate(
                self.recovery_interrupted_failed > 0,
                self.recovery_interrupted_failed,
            ),
            "cleanup_after_success": _gate(successful_runs > 0, successful_runs),
            "cleanup_after_failure": _gate(
                failed_cleanup_runs > 0, failed_cleanup_runs
            ),
            "retention_policy_observed": _gate(
                self.latest_retention_policy is not None,
                self.retention_policy_events,
            ),
            "retention_sweep_deletion": _gate(
                self.cleanup_deleted_total > 0 and self.cleanup_success > 0,
                self.cleanup_deleted_total,
            ),
            "dependencies_ready": _gate(health_ready, 1 if health_ready else 0),
        }
        ready = all(
            isinstance(check, dict) and check.get("status") == "PASS"
            for check in checks.values()
        )
        return {
            "machine_verifiable_ready": ready,
            "checks": checks,
            "manual_review_remaining": [
                "russian_ux_coverage",
                "english_ux_coverage",
            ],
        }

    def _multi_file_success(self, operation_id: str) -> int:
        operation = self.operations.get(operation_id)
        if operation is None:
            return 0
        return operation.multi_file_e2e_success_count()


def summarize_lines(lines: Iterable[str]) -> dict[str, object]:
    accumulator = _EvidenceAccumulator()
    for line in lines:
        payload = _parse_payload(line)
        if payload is not None:
            accumulator.consume(payload)
    return accumulator.to_payload()


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


def _admin_summary(payload: dict[str, object]) -> dict[str, object]:
    health_ready: bool | None = None
    health = payload.get("health")
    if isinstance(health, dict):
        ready = cast(dict[str, Any], health).get("ready")
        if isinstance(ready, bool):
            health_ready = ready

    failure_classes: list[dict[str, object]] = []
    metrics = payload.get("metrics")
    if isinstance(metrics, dict):
        raw_classes = cast(dict[str, Any], metrics).get("failure_classes")
        if isinstance(raw_classes, list):
            for item in raw_classes:
                if not isinstance(item, dict):
                    continue
                raw = cast(dict[str, Any], item)
                operation_id = raw.get("operation_id")
                stage = raw.get("stage")
                error_code = raw.get("error_code")
                count = raw.get("count")
                if (
                    isinstance(operation_id, str)
                    and isinstance(stage, str)
                    and isinstance(error_code, str)
                    and _integer(count) is not None
                ):
                    failure_classes.append(
                        {
                            "operation_id": operation_id,
                            "stage": stage,
                            "error_code": error_code,
                            "count": _integer(count),
                        }
                    )

    failure_classes.sort(
        key=lambda item: (
            str(item["operation_id"]),
            str(item["stage"]),
            str(item["error_code"]),
        )
    )
    return {
        "health_ready": health_ready,
        "failure_classes": failure_classes,
    }


def _gate(passed: bool, observed: int) -> dict[str, object]:
    return {
        "status": "PASS" if passed else "PENDING",
        "observed": observed,
    }


def _string(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _integer(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Summarize privacy-safe SimpleConvBot private-alpha telemetry."
    )
    parser.add_argument(
        "--input",
        type=Path,
        help="Read logs from this UTF-8 file instead of stdin.",
    )
    parser.add_argument(
        "--require-runtime-gates",
        action="store_true",
        help=(
            "Exit with status 2 unless all machine-verifiable runtime gates pass. "
            "Manual RU/EN review is still required separately."
        ),
    )
    args = parser.parse_args(argv)

    if args.input is None:
        summary = summarize_lines(sys.stdin)
    else:
        with args.input.open("r", encoding="utf-8", errors="replace") as stream:
            summary = summarize_lines(stream)

    json.dump(summary, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    if args.require_runtime_gates:
        gates = summary.get("runtime_gates")
        if not isinstance(gates, dict) or gates.get("machine_verifiable_ready") is not True:
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
