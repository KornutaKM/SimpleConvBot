from __future__ import annotations

import os
from pathlib import Path


def _proc_status() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in Path("/proc/self/status").read_text(encoding="utf-8").splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        values[key] = value.strip()
    return values


def main() -> int:
    if os.geteuid() == 0:
        raise RuntimeError("production container must not run as root")

    status = _proc_status()
    if status.get("NoNewPrivs") != "1":
        raise RuntimeError("no-new-privileges is not active")
    if int(status.get("CapEff", "1"), 16) != 0:
        raise RuntimeError("effective Linux capabilities are not empty")

    interfaces = {path.name for path in Path("/sys/class/net").iterdir()}
    if interfaces != {"lo"}:
        raise RuntimeError(f"worker network is not isolated: {sorted(interfaces)}")

    root_probe = Path("/app/.security-rootfs-probe")
    try:
        root_probe.write_text("unexpected", encoding="utf-8")
    except OSError:
        pass
    else:
        root_probe.unlink(missing_ok=True)
        raise RuntimeError("container root filesystem is writable")

    temp_root = Path(os.environ.get("TEMP_ROOT", "/app/var/jobs"))
    temp_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    workspace_probe = temp_root / ".security-workspace-probe"
    workspace_probe.write_text("ok", encoding="utf-8")
    workspace_probe.unlink()

    print("SECURITY_SELFTEST=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
