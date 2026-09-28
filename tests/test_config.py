from pathlib import Path

import pytest

from simpleconvbot.config import Environment, Settings, SettingsError


def test_settings_defaults() -> None:
    settings = Settings.from_mapping({})

    assert settings.environment is Environment.DEVELOPMENT
    assert settings.log_level == "INFO"
    assert settings.telegram_bot_token is None
    assert settings.redis_url == "redis://localhost:6379/0"
    assert settings.temp_root == Path("var/jobs")
    assert settings.temp_ttl_seconds == 3600


def test_settings_parse_values() -> None:
    settings = Settings.from_mapping(
        {
            "APP_ENV": "production",
            "LOG_LEVEL": "warning",
            "TELEGRAM_BOT_TOKEN": " secret-token ",
            "DATABASE_URL": "postgresql://db/service",
            "REDIS_URL": "redis://cache:6379/1",
            "TEMP_ROOT": "/tmp/simpleconvbot",
            "TEMP_TTL_SECONDS": "900",
        }
    )

    assert settings.environment is Environment.PRODUCTION
    assert settings.log_level == "WARNING"
    assert settings.telegram_bot_token == "secret-token"
    assert settings.database_url == "postgresql+asyncpg://db/service"
    assert settings.redis_url == "redis://cache:6379/1"
    assert settings.temp_root == Path("/tmp/simpleconvbot")
    assert settings.temp_ttl_seconds == 900


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "postgresql://db.internal:5432/app?sslmode=require",
            "postgresql+asyncpg://db.internal:5432/app?sslmode=require",
        ),
        (
            "postgres://db.internal:5432/app",
            "postgresql+asyncpg://db.internal:5432/app",
        ),
        (
            "postgresql+asyncpg://db.internal:5432/app",
            "postgresql+asyncpg://db.internal:5432/app",
        ),
    ],
)
def test_provider_postgres_urls_use_asyncpg_driver(raw: str, expected: str) -> None:
    settings = Settings.from_mapping({"DATABASE_URL": raw})

    assert settings.database_url == expected


@pytest.mark.parametrize("raw", ["0", "-1", "abc"])
def test_temp_ttl_must_be_positive_integer(raw: str) -> None:
    with pytest.raises(SettingsError):
        Settings.from_mapping({"TEMP_TTL_SECONDS": raw})


def test_environment_is_validated() -> None:
    with pytest.raises(SettingsError, match="APP_ENV must be one of"):
        Settings.from_mapping({"APP_ENV": "staging"})


def test_runtime_requires_bot_token() -> None:
    settings = Settings.from_mapping({})

    with pytest.raises(SettingsError, match="TELEGRAM_BOT_TOKEN"):
        settings.validate_runtime()


def test_runtime_accepts_complete_settings() -> None:
    settings = Settings.from_mapping({"TELEGRAM_BOT_TOKEN": "token"})

    settings.validate_runtime()


def test_token_is_redacted_from_repr() -> None:
    settings = Settings.from_mapping({"TELEGRAM_BOT_TOKEN": "super-secret-value"})

    assert "super-secret-value" not in repr(settings)
