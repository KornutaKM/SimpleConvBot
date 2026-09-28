from __future__ import annotations

import asyncio
import sys

from simpleconvbot import __version__
from simpleconvbot.runtime import run_polling


def main() -> int:
    if "--version" in sys.argv[1:]:
        print(f"SimpleConvBot {__version__}")
        return 0

    asyncio.run(run_polling())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
