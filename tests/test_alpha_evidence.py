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
        _log({"event": "recovery_summary", "outcome": "success", "count": 0}),
        _log({"event": "recovery_summary", "outcome": "success", "count": 3}),
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
    assert summary["recovery"] == {
        "summary_events": 2,
        "clean_summary_events": 1,
        "actions_total": 3,
    }
    assert summary["retention_cleanup"] == {
        "events": 2,
        "success": 1,
        "failure": 1,
        "deleted_total": 2,
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
        "user_id",
        "chat_id",
        "file_path",
        "token",
        "999",
        "888",
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
