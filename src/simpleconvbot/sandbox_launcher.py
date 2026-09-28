from __future__ import annotations

import json
import os
import resource
import sys
import time
from pathlib import Path
from typing import Any

_RESULT = Path(".sandbox-result.json")


def _positive_env_int(name: str) -> int:
    raw = os.environ.get(name)
    if raw is None:
        raise RuntimeError(f"missing sandbox limit: {name}")
    value = int(raw)
    if value <= 0:
        raise RuntimeError(f"invalid sandbox limit: {name}")
    return value


def _apply_limits() -> None:
    cpu = _positive_env_int("SCB_SANDBOX_CPU_SECONDS")
    address_space = _positive_env_int("SCB_SANDBOX_ADDRESS_SPACE_BYTES")
    file_size = _positive_env_int("SCB_SANDBOX_FILE_SIZE_BYTES")
    open_files = _positive_env_int("SCB_SANDBOX_OPEN_FILES")
    processes = _positive_env_int("SCB_SANDBOX_PROCESSES")

    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
    resource.setrlimit(resource.RLIMIT_AS, (address_space, address_space))
    resource.setrlimit(resource.RLIMIT_FSIZE, (file_size, file_size))
    resource.setrlimit(resource.RLIMIT_NOFILE, (open_files, open_files))
    resource.setrlimit(resource.RLIMIT_NPROC, (processes, processes))
    os.umask(0o077)


def _read_request(name: str) -> dict[str, Any]:
    if Path(name).name != name or name != ".sandbox-request.json":
        raise RuntimeError("invalid sandbox request name")
    raw = Path(name).read_text(encoding="utf-8")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise RuntimeError("sandbox request must be an object")
    return value


def _run_probe(request: dict[str, Any]) -> dict[str, Any]:
    action = request.get("action")
    if action == "env":
        return {
            "status": "ok",
            "telegram_token_present": "TELEGRAM_BOT_TOKEN" in os.environ,
            "database_url_present": "DATABASE_URL" in os.environ,
            "redis_url_present": "REDIS_URL" in os.environ,
        }

    if action == "cwd":
        return {"status": "ok", "cwd": str(Path.cwd())}

    if action == "sleep":
        seconds = float(request.get("seconds", 0))
        if seconds < 0 or seconds > 300:
            raise RuntimeError("invalid sleep probe")
        time.sleep(seconds)
        return {"status": "ok", "slept": seconds}

    if action == "write":
        byte_count = int(request.get("bytes", 0))
        if byte_count < 0 or byte_count > 512 * 1024 * 1024:
            raise RuntimeError("invalid write probe")
        chunk = b"x" * min(1024 * 1024, max(1, byte_count))
        remaining = byte_count
        with Path("sandbox-payload.bin").open("wb") as output:
            while remaining:
                piece = chunk[: min(len(chunk), remaining)]
                output.write(piece)
                remaining -= len(piece)
        return {"status": "ok", "bytes": byte_count}

    raise RuntimeError("unknown sandbox probe action")


def main() -> int:
    if len(sys.argv) != 3:
        return 2
    program, request_name = sys.argv[1:]
    _apply_limits()
    request = _read_request(request_name)

    if program == "probe":
        result = _run_probe(request)
    else:
        return 2

    _RESULT.write_text(
        json.dumps(result, separators=(",", ":"), ensure_ascii=True),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
