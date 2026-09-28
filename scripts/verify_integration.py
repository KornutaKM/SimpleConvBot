from __future__ import annotations

import subprocess
import sys


def main() -> int:
    command = [sys.executable, "-m", "pytest", "-m", "integration"]
    print("+", " ".join(command), flush=True)
    subprocess.run(command, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
