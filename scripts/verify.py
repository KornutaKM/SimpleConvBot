from __future__ import annotations

import subprocess
import sys
from collections.abc import Sequence


def run(args: Sequence[str]) -> None:
    command = [sys.executable, "-m", *args]
    print("+", " ".join(command), flush=True)
    subprocess.run(command, check=True)


def main() -> int:
    run(("ruff", "format", "--diff", "src/simpleconvbot/recovery.py"))
    run(("ruff", "format", "--check", "."))
    run(("ruff", "check", "."))
    run(("mypy", "src", "tests"))
    run(("pytest", "-m", "not integration"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
