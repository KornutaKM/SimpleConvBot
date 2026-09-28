from __future__ import annotations

import sys
from pathlib import Path

import pytest

from simpleconvbot.sandbox import SandboxError, SandboxErrorCode, SandboxLimits, SandboxRunner


pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Linux resource sandbox only")


def test_sandbox_child_does_not_inherit_application_secrets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "should-not-cross-boundary")
    monkeypatch.setenv("DATABASE_URL", "postgresql://secret")
    monkeypatch.setenv("REDIS_URL", "redis://secret")

    result = SandboxRunner().run_probe(tmp_path, {"action": "env"})

    assert result["telegram_token_present"] is False
    assert result["database_url_present"] is False
    assert result["redis_url_present"] is False


def test_sandbox_runs_inside_job_workspace(tmp_path: Path) -> None:
    result = SandboxRunner().run_probe(tmp_path, {"action": "cwd"})

    assert Path(str(result["cwd"])) == tmp_path.resolve()


def test_sandbox_wall_timeout_kills_child(tmp_path: Path) -> None:
    runner = SandboxRunner(SandboxLimits(wall_seconds=0.1))

    with pytest.raises(SandboxError) as captured:
        runner.run_probe(tmp_path, {"action": "sleep", "seconds": 2})

    assert captured.value.code is SandboxErrorCode.TIMEOUT


def test_sandbox_file_size_limit_terminates_oversize_writer(tmp_path: Path) -> None:
    runner = SandboxRunner(
        SandboxLimits(
            wall_seconds=5,
            file_size_bytes=1024 * 1024,
        )
    )

    with pytest.raises(SandboxError) as captured:
        runner.run_probe(tmp_path, {"action": "write", "bytes": 2 * 1024 * 1024})

    assert captured.value.code is SandboxErrorCode.CHILD_FAILED
