from __future__ import annotations

import json

import pytest
from scripts.bot_profile import main

from simpleconvbot.bot_profile import PRIVACY_URL, PUBLIC_PROFILES


def test_public_profiles_fit_telegram_limits_and_link_privacy() -> None:
    assert PRIVACY_URL.startswith("https://")
    assert PUBLIC_PROFILES

    for profile in PUBLIC_PROFILES:
        assert 0 < len(profile.name) <= 64
        assert 0 < len(profile.short_description) <= 120
        assert 0 < len(profile.description) <= 512
        assert PRIVACY_URL in profile.description

    assert PUBLIC_PROFILES[0].language_code == ""
    assert PUBLIC_PROFILES[1].language_code == "ru"


def test_profile_copy_advertises_only_enabled_top_level_families() -> None:
    fallback = PUBLIC_PROFILES[0]
    russian = PUBLIC_PROFILES[1]

    for expected in ("JPG", "PNG", "WebP", "PDF", "MP3", "M4A", "WAV", "GIF"):
        assert expected in fallback.description

    for expected in ("JPG", "PNG", "WebP", "PDF", "MP3", "M4A", "WAV", "GIF"):
        assert expected in russian.description

    for forbidden in ("archive", "QR", "OCR", "ZIP"):
        assert forbidden not in fallback.description


def test_profile_tool_is_dry_run_without_token(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)

    assert main([]) == 0

    output = capsys.readouterr().out
    assert "Dry run only" in output
    payload = json.loads(output.split("\nDry run only", maxsplit=1)[0])
    assert payload["mode"] == "profile_apply_plan"
    assert payload["profiles"][0]["name"] == "SimpleConv"


def test_profile_tool_requires_token_for_apply(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)

    with pytest.raises(SystemExit, match="TELEGRAM_BOT_TOKEN"):
        main(["--apply"])
