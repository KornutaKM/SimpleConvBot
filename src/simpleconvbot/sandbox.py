from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any


class SandboxErrorCode(StrEnum):
    UNSUPPORTED_PLATFORM = "sandbox_unsupported_platform"
    INVALID_WORKSPACE = "sandbox_invalid_workspace"
    TIMEOUT = "sandbox_timeout"
    CHILD_FAILED = "sandbox_child_failed"
    INVALID_RESULT = "sandbox_invalid_result"


class SandboxError(RuntimeError):
    def __init__(self, code: SandboxErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code


class SandboxProgram(StrEnum):
    PROBE = "probe"


@dataclass(frozen=True, slots=True)
class SandboxLimits:
    wall_seconds: float = 30.0
    cpu_seconds: int = 15
    address_space_bytes: int = 512 * 1024 * 1024
    file_size_bytes: int = 64 * 1024 * 1024
    open_files: int = 64
    processes: int = 32
    result_bytes: int = 64 * 1024

    def __post_init__(self) -> None:
        for name, value in (
            ("wall_seconds", self.wall_seconds),
            ("cpu_seconds", self.cpu_seconds),
            ("address_space_bytes", self.address_space_bytes),
            ("file_size_bytes", self.file_size_bytes),
            ("open_files", self.open_files),
            ("processes", self.processes),
            ("result_bytes", self.result_bytes),
        ):
            if value <= 0:
                raise ValueError(f"{name} must be greater than zero")


class SandboxRunner:
    _REQUEST = ".sandbox-request.json"
    _RESULT = ".sandbox-result.json"

    def __init__(
        self,
        limits: SandboxLimits | None = None,
        *,
        python_executable: Path | None = None,
    ) -> None:
        self._limits = limits or SandboxLimits()
        self._python = (python_executable or Path(sys.executable)).resolve()

    def run_probe(self, workspace: Path, payload: dict[str, Any]) -> dict[str, Any]:
        return self._run(SandboxProgram.PROBE, workspace, payload)

    def _run(
        self,
        program: SandboxProgram,
        workspace: Path,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        if sys.platform != "linux":
            raise SandboxError(
                SandboxErrorCode.UNSUPPORTED_PLATFORM,
                "resource sandbox is supported only on Linux",
            )

        resolved = workspace.resolve(strict=True)
        if workspace.is_symlink() or not resolved.is_dir():
            raise SandboxError(
                SandboxErrorCode.INVALID_WORKSPACE,
                "sandbox workspace must be a real directory",
            )

        request_path = resolved / self._REQUEST
        result_path = resolved / self._RESULT
        if request_path.is_symlink() or result_path.is_symlink():
            raise SandboxError(
                SandboxErrorCode.INVALID_WORKSPACE,
                "sandbox control files must not be symlinks",
            )

        request_path.write_text(
            json.dumps(payload, separators=(",", ":"), ensure_ascii=True),
            encoding="utf-8",
        )
        request_path.chmod(0o400)
        result_path.unlink(missing_ok=True)

        env = {
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "LANG": "C",
            "LC_ALL": "C",
            "PYTHONUNBUFFERED": "1",
            "SCB_SANDBOX_CPU_SECONDS": str(self._limits.cpu_seconds),
            "SCB_SANDBOX_ADDRESS_SPACE_BYTES": str(self._limits.address_space_bytes),
            "SCB_SANDBOX_FILE_SIZE_BYTES": str(self._limits.file_size_bytes),
            "SCB_SANDBOX_OPEN_FILES": str(self._limits.open_files),
            "SCB_SANDBOX_PROCESSES": str(self._limits.processes),
        }

        argv = (
            str(self._python),
            "-I",
            "-m",
            "simpleconvbot.sandbox_launcher",
            program.value,
            self._REQUEST,
        )
        process = subprocess.Popen(
            argv,
            cwd=resolved,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            shell=False,
        )
        try:
            returncode = process.wait(timeout=self._limits.wall_seconds)
        except subprocess.TimeoutExpired as exc:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            raise SandboxError(
                SandboxErrorCode.TIMEOUT,
                "sandbox child exceeded wall-clock timeout",
            ) from exc
        finally:
            request_path.unlink(missing_ok=True)

        if returncode != 0:
            result_path.unlink(missing_ok=True)
            raise SandboxError(
                SandboxErrorCode.CHILD_FAILED,
                f"sandbox child exited with code {returncode}",
            )

        try:
            stat = result_path.stat(follow_symlinks=False)
            if result_path.is_symlink() or not result_path.is_file():
                raise SandboxError(
                    SandboxErrorCode.INVALID_RESULT,
                    "sandbox result is not a regular file",
                )
            if stat.st_size > self._limits.result_bytes:
                raise SandboxError(
                    SandboxErrorCode.INVALID_RESULT,
                    "sandbox result exceeded byte limit",
                )
            raw = result_path.read_text(encoding="utf-8")
            value = json.loads(raw)
            if not isinstance(value, dict) or value.get("status") != "ok":
                raise SandboxError(
                    SandboxErrorCode.INVALID_RESULT,
                    "sandbox result schema is invalid",
                )
            return value
        except (OSError, json.JSONDecodeError) as exc:
            raise SandboxError(
                SandboxErrorCode.INVALID_RESULT,
                "sandbox result could not be read",
            ) from exc
        finally:
            result_path.unlink(missing_ok=True)
