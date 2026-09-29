from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

from simpleconvbot.alpha_evidence import main, summarize_lines


def _log(payload: dict[str, object]) -> str:
    return f"app-1  | INFO:simpleconvbot.test:{json.dumps(payload, separators=(',', ':'))}\n"


def _mapping(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    return cast(dict[str, object], value)


def _list(value: object) -> list[object]:
    assert isinstance(value, list)
    return cast(list[object], value)


def test_summary_proves_e2e_multifile_dedup_recovery_and_cleanup_without_identity() -> None:
    correlation_id = "0123456789abcdef"
    lines = [
        "app-1 | ordinary non-JSON log line\n",
        _log(
            {
                "event": "operation_stage",
                "operation_id": "pdf.merge",
                "stage": "validation",
                "outcome": "success",
                "duration_ms": 10,
                "correlation_id": correlation_id,
                "count": 2,
            }
        ),
        *[
            _log(
                {
                    "event": "operation_stage",
                    "operation_id": "pdf.merge",
                    "stage": stage,
                    "outcome": "success",
                    "duration_ms": 1,
                    "correlation_id": correlation_id,
                }
            )
            for stage in ("queue", "worker", "upload", "cleanup")
        ],
        _log(
            {
                "event": "operation_stage",
                "operation_id": "image.to_png",
                "stage": "validation",
                "outcome": "success",
                "duration_ms": 5,
                "correlation_id": "fedcba9876543210",
            }
        ),
        _log({"event": "update_deduplicated", "outcome": "success", "count": 1}),
        _log(
            {
                "event": "input_rejected",
                "outcome": "failure",
                "error_code": "unsupported_document",
                "count": 1,
                "filename": "private.zip",
                "user_id": 123,
            }
        ),
        _log(
            {
                "event": "input_rejected",
                "operation_id": "image.to_png",
                "outcome": "failure",
                "error_code": "telegram_input_too_large",
                "count": 1,
                "chat_id": 456,
            }
        ),
        _log({"event": "recovery_summary", "outcome": "success", "count": 0}),
        _log({"event": "recovery_summary", "outcome": "success", "count": 3}),
        _log(
            {
                "event": "retention_policy",
                "ttl_seconds": 3600,
                "interval_seconds": 60,
                "user_id": 777,
            }
        ),
        _log({"event": "cleanup", "outcome": "success", "count": 2}),
        _log({"event": "cleanup", "outcome": "failure", "count": 0}),
        _log(
            {
                "event": "admin_diagnostic",
                "health": {"ready": True},
                "metrics": {
                    "failure_classes": [
                        {
                            "operation_id": "video.compress",
                            "stage": "worker",
                            "error_code": "media_timeout",
                            "count": 2,
                        }
                    ]
                },
                "user_id": 999,
                "filename": "passport.pdf",
            }
        ),
        _log(
            {
                "event": "unknown_private_event",
                "user_id": 999,
                "chat_id": 888,
                "file_path": "documents/private.pdf",
                "token": "secret",
            }
        ),
    ]

    summary = summarize_lines(lines)

    operations = _mapping(summary["operations"])
    merge = _mapping(operations["pdf.merge"])
    merge_runs = _mapping(merge["runs"])
    assert merge_runs == {
        "observed": 1,
        "e2e_success": 1,
        "multi_file_e2e_success": 1,
    }
    assert merge["validation_input_counts"] == [2]

    image = _mapping(operations["image.to_png"])
    image_runs = _mapping(image["runs"])
    assert image_runs["observed"] == 1
    assert image_runs["e2e_success"] == 0

    assert summary["duplicate_updates"] == {"events": 1, "dropped_total": 1}
    assert summary["input_rejections"] == {
        "events": 2,
        "by_error_code": {
            "telegram_input_too_large": 1,
            "unsupported_document": 1,
        },
    }
    assert summary["recovery"] == {
        "summary_events": 2,
        "clean_summary_events": 1,
        "actions_total": 3,
        "inflight_queue_items": 0,
        "interrupted_failed": 0,
        "queued_reenqueued": 0,
    }
    assert summary["retention_cleanup"] == {
        "events": 2,
        "success": 1,
        "failure": 1,
        "deleted_total": 2,
    }
    assert summary["retention_policy"] == {
        "events": 1,
        "latest": {
            "ttl_seconds": 3600,
            "sweep_interval_seconds": 60,
            "max_cleanup_delay_seconds": 3660,
        },
    }

    admin = _mapping(summary["latest_admin_diagnostic"])
    assert admin["health_ready"] is True
    failure_classes = _list(admin["failure_classes"])
    assert failure_classes == [
        {
            "operation_id": "video.compress",
            "stage": "worker",
            "error_code": "media_timeout",
            "count": 2,
        }
    ]

    serialized = json.dumps(summary, sort_keys=True)
    for forbidden in (
        "passport.pdf",
        "private.pdf",
        "private.zip",
        "user_id",
        "chat_id",
        "file_path",
        "token",
        "999",
        "888",
        "777",
    ):
        assert forbidden not in serialized


def test_cli_reads_log_file_and_writes_only_summary(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "runtime.log"
    source.write_text(
        _log({"event": "update_deduplicated", "outcome": "success", "count": 2}),
        encoding="utf-8",
    )

    assert main(["--input", str(source)]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["duplicate_updates"] == {"events": 1, "dropped_total": 2}


def test_runtime_gate_evaluator_requires_specific_recovery_and_cleanup_evidence() -> None:
    lines: list[str] = []

    for operation_id, correlation_id in (
        ("pdf.from_images", "1111111111111111"),
        ("pdf.merge", "2222222222222222"),
        ("image.to_png", "3333333333333333"),
    ):
        lines.append(
            _log(
                {
                    "event": "operation_stage",
                    "operation_id": operation_id,
                    "stage": "validation",
                    "outcome": "success",
                    "duration_ms": 1,
                    "correlation_id": correlation_id,
                    "count": 2 if operation_id.startswith("pdf.") else None,
                }
            )
        )
        for stage in ("queue", "worker", "upload", "cleanup"):
            lines.append(
                _log(
                    {
                        "event": "operation_stage",
                        "operation_id": operation_id,
                        "stage": stage,
                        "outcome": "success",
                        "duration_ms": 1,
                        "correlation_id": correlation_id,
                    }
                )
            )

    lines.extend(
        [
            _log(
                {
                    "event": "operation_stage",
                    "operation_id": "video.compress",
                    "stage": "worker",
                    "outcome": "failure",
                    "duration_ms": 2,
                    "error_code": "media_timeout",
                    "correlation_id": "4444444444444444",
                }
            ),
            _log(
                {
                    "event": "operation_stage",
                    "operation_id": "video.compress",
                    "stage": "cleanup",
                    "outcome": "success",
                    "duration_ms": 1,
                    "correlation_id": "4444444444444444",
                }
            ),
            _log({"event": "update_deduplicated", "outcome": "success", "count": 1}),
            _log(
                {
                    "event": "input_rejected",
                    "outcome": "failure",
                    "error_code": "unsupported_document",
                    "count": 1,
                }
            ),
            _log(
                {
                    "event": "input_rejected",
                    "operation_id": "image.to_png",
                    "outcome": "failure",
                    "error_code": "telegram_input_too_large",
                    "count": 1,
                }
            ),
            _log(
                {
                    "event": "recovery",
                    "operation_id": "image.to_png",
                    "outcome": "failure",
                    "error_code": "restart_interrupted",
                    "correlation_id": "5555555555555555",
                }
            ),
            _log({"event": "recovery_summary", "outcome": "success", "count": 1}),
            _log({"event": "retention_policy", "ttl_seconds": 3600, "interval_seconds": 60}),
            _log({"event": "cleanup", "outcome": "success", "count": 1}),
            _log(
                {
                    "event": "admin_diagnostic",
                    "health": {"ready": True},
                    "metrics": {"failure_classes": []},
                }
            ),
        ]
    )

    summary = summarize_lines(lines)

    recovery = _mapping(summary["recovery"])
    assert recovery["interrupted_failed"] == 1
    assert recovery["queued_reenqueued"] == 0
    assert recovery["inflight_queue_items"] == 0

    gates = _mapping(summary["runtime_gates"])
    assert gates["machine_verifiable_ready"] is True
    checks = _mapping(gates["checks"])
    assert all(_mapping(value)["status"] == "PASS" for value in checks.values())
    assert gates["manual_review_remaining"] == [
        "russian_ux_coverage",
        "english_ux_coverage",
    ]


def test_cli_require_runtime_gates_returns_two_when_evidence_is_incomplete(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "runtime.log"
    source.write_text(
        _log({"event": "update_deduplicated", "outcome": "success", "count": 1}),
        encoding="utf-8",
    )

    assert main(["--input", str(source), "--require-runtime-gates"]) == 2

    payload = json.loads(capsys.readouterr().out)
    gates = _mapping(payload["runtime_gates"])
    assert gates["machine_verifiable_ready"] is False
