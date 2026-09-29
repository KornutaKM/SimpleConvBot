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
    assert settings.retention_sweep_interval_seconds == 60
    assert settings.diagnostics_interval_seconds == 300
    assert settings.workspace_max_bytes == 64 * 1024 * 1024
    assert settings.update_rate_limit_per_minute == 60
    assert settings.max_active_jobs_per_user == 3
    assert settings.max_active_jobs_global == 32


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
            "RETENTION_SWEEP_INTERVAL_SECONDS": "45",
            "DIAGNOSTICS_INTERVAL_SECONDS": "120",
            "WORKSPACE_MAX_BYTES": "12345",
            "UPDATE_RATE_LIMIT_PER_MINUTE": "12",
            "MAX_ACTIVE_JOBS_PER_USER": "2",
            "MAX_ACTIVE_JOBS_GLOBAL": "9",
        }
    )

    assert settings.environment is Environment.PRODUCTION
    assert settings.log_level == "WARNING"
    assert settings.telegram_bot_token == "secret-token"
    assert settings.database_url == "postgresql+asyncpg://db/service"
    assert settings.redis_url == "redis://cache:6379/1"
    assert settings.temp_root == Path("/tmp/simpleconvbot")
    assert settings.temp_ttl_seconds == 900
    assert settings.retention_sweep_interval_seconds == 45
    assert settings.diagnostics_interval_seconds == 120
    assert settings.workspace_max_bytes == 12345
    assert settings.update_rate_limit_per_minute == 12
    assert settings.max_active_jobs_per_user == 2
    assert settings.max_active_jobs_global == 9


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


@pytest.mark.parametrize(
    "name",
    [
        "TEMP_TTL_SECONDS",
        "RETENTION_SWEEP_INTERVAL_SECONDS",
        "DIAGNOSTICS_INTERVAL_SECONDS",
        "WORKSPACE_MAX_BYTES",
        "UPDATE_RATE_LIMIT_PER_MINUTE",
        "MAX_ACTIVE_JOBS_PER_USER",
        "MAX_ACTIVE_JOBS_GLOBAL",
    ],
)
@pytest.mark.parametrize("raw", ["0", "-1", "abc"])
def test_positive_security_limits_are_validated(name: str, raw: str) -> None:
    with pytest.raises(SettingsError):
        Settings.from_mapping({name: raw})


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


def test_credentials_are_redacted_from_repr() -> None:
    settings = Settings.from_mapping(
        {
            "TELEGRAM_BOT_TOKEN": "super-secret-token",
            "DATABASE_URL": "postgresql://db-user:db-secret@db.internal/app",
            "REDIS_URL": "redis://default:redis-secret@cache.internal:6379/0",
        }
    )

    rendered = repr(settings)
    assert "super-secret-token" not in rendered
    assert "db-secret" not in rendered
    assert "redis-secret" not in rendered


def test_retention_sweep_interval_cannot_exceed_temp_ttl() -> None:
    with pytest.raises(SettingsError, match="must not exceed TEMP_TTL_SECONDS"):
        Settings.from_mapping(
            {
                "TEMP_TTL_SECONDS": "60",
                "RETENTION_SWEEP_INTERVAL_SECONDS": "61",
            }
        )
