from __future__ import annotations

import argparse
import asyncio
import json
import os
from dataclasses import asdict
from typing import Sequence

from aiogram import Bot

from simpleconvbot.bot_profile import PUBLIC_PROFILES


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Review or explicitly apply the canonical public Telegram bot profile."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the canonical profile through Telegram Bot API. Without this flag, dry-run only.",
    )
    return parser


def _render_plan() -> str:
    return json.dumps(
        {
            "mode": "profile_apply_plan",
            "profiles": [asdict(profile) for profile in PUBLIC_PROFILES],
        },
        ensure_ascii=False,
        indent=2,
    )


async def _apply(token: str) -> None:
    bot = Bot(token=token)
    try:
        for profile in PUBLIC_PROFILES:
            language_code = profile.language_code or None
            await bot.set_my_name(
                name=profile.name,
                language_code=language_code,
            )
            await bot.set_my_short_description(
                short_description=profile.short_description,
                language_code=language_code,
            )
            await bot.set_my_description(
                description=profile.description,
                language_code=language_code,
            )
    finally:
        await bot.session.close()


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    print(_render_plan())

    if not args.apply:
        print("Dry run only. Re-run with --apply to change the Telegram profile.")
        return 0

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit("TELEGRAM_BOT_TOKEN is required with --apply")

    asyncio.run(_apply(token))
    print("Canonical Telegram profile applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
