from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from os import environ
from pathlib import Path


class SettingsError(ValueError):
    """Raised when configuration is invalid or incomplete."""


class Environment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


@dataclass(frozen=True, slots=True)
class Settings:
    environment: Environment = Environment.DEVELOPMENT
    log_level: str = "INFO"
    telegram_bot_token: str | None = field(default=None, repr=False)
    database_url: str = field(
        default="postgresql+asyncpg://simpleconvbot@localhost:5432/simpleconvbot",
        repr=False,
    )
    redis_url: str = field(default="redis://localhost:6379/0", repr=False)
    temp_root: Path = Path("var/jobs")
    temp_ttl_seconds: int = 3600
    metadata_ttl_seconds: int = 7 * 24 * 60 * 60
    retention_sweep_interval_seconds: int = 60
    diagnostics_interval_seconds: int = 300
    workspace_max_bytes: int = 64 * 1024 * 1024
    update_rate_limit_per_minute: int = 60
    max_active_jobs_per_user: int = 3
    max_active_jobs_global: int = 32

    @classmethod
    def from_env(cls) -> Settings:
        return cls.from_mapping(environ)

    @classmethod
    def from_mapping(cls, values: Mapping[str, str]) -> Settings:
        environment = _parse_environment(values.get("APP_ENV", Environment.DEVELOPMENT.value))
        log_level = values.get("LOG_LEVEL", "INFO").strip().upper()
        if not log_level:
            raise SettingsError("LOG_LEVEL must not be empty")

        temp_ttl_seconds = _parse_positive_int(
            "TEMP_TTL_SECONDS",
            values.get("TEMP_TTL_SECONDS", "3600"),
        )
        metadata_ttl_seconds = _parse_positive_int(
            "METADATA_TTL_SECONDS",
            values.get("METADATA_TTL_SECONDS", str(7 * 24 * 60 * 60)),
        )
        retention_sweep_interval_seconds = _parse_positive_int(
            "RETENTION_SWEEP_INTERVAL_SECONDS",
            values.get("RETENTION_SWEEP_INTERVAL_SECONDS", "60"),
        )
        if retention_sweep_interval_seconds > temp_ttl_seconds:
            raise SettingsError("RETENTION_SWEEP_INTERVAL_SECONDS must not exceed TEMP_TTL_SECONDS")
        if retention_sweep_interval_seconds > metadata_ttl_seconds:
            raise SettingsError(
                "RETENTION_SWEEP_INTERVAL_SECONDS must not exceed METADATA_TTL_SECONDS"
            )
        diagnostics_interval_seconds = _parse_positive_int(
            "DIAGNOSTICS_INTERVAL_SECONDS",
            values.get("DIAGNOSTICS_INTERVAL_SECONDS", "300"),
        )
        workspace_max_bytes = _parse_positive_int(
            "WORKSPACE_MAX_BYTES",
            values.get("WORKSPACE_MAX_BYTES", str(64 * 1024 * 1024)),
        )
        update_rate_limit_per_minute = _parse_positive_int(
            "UPDATE_RATE_LIMIT_PER_MINUTE",
            values.get("UPDATE_RATE_LIMIT_PER_MINUTE", "60"),
        )
        max_active_jobs_per_user = _parse_positive_int(
            "MAX_ACTIVE_JOBS_PER_USER",
            values.get("MAX_ACTIVE_JOBS_PER_USER", "3"),
        )
        max_active_jobs_global = _parse_positive_int(
            "MAX_ACTIVE_JOBS_GLOBAL",
            values.get("MAX_ACTIVE_JOBS_GLOBAL", "32"),
        )

        database_url = _normalize_database_url(
            values.get(
                "DATABASE_URL",
                "postgresql+asyncpg://simpleconvbot@localhost:5432/simpleconvbot",
            ).strip()
        )

        return cls(
            environment=environment,
            log_level=log_level,
            telegram_bot_token=_optional_secret(values.get("TELEGRAM_BOT_TOKEN")),
            database_url=database_url,
            redis_url=values.get("REDIS_URL", "redis://localhost:6379/0").strip(),
            temp_root=Path(values.get("TEMP_ROOT", "var/jobs")).expanduser(),
            temp_ttl_seconds=temp_ttl_seconds,
            metadata_ttl_seconds=metadata_ttl_seconds,
            retention_sweep_interval_seconds=retention_sweep_interval_seconds,
            diagnostics_interval_seconds=diagnostics_interval_seconds,
            workspace_max_bytes=workspace_max_bytes,
            update_rate_limit_per_minute=update_rate_limit_per_minute,
            max_active_jobs_per_user=max_active_jobs_per_user,
            max_active_jobs_global=max_active_jobs_global,
        )

    def validate_runtime(self) -> None:
        if not self.telegram_bot_token:
            raise SettingsError("TELEGRAM_BOT_TOKEN is required for bot runtime")
        if not self.database_url:
            raise SettingsError("DATABASE_URL must not be empty")
        if not self.redis_url:
            raise SettingsError("REDIS_URL must not be empty")


def _parse_environment(raw: str) -> Environment:
    try:
        return Environment(raw.strip().lower())
    except ValueError as exc:
        allowed = ", ".join(item.value for item in Environment)
        raise SettingsError(f"APP_ENV must be one of: {allowed}") from exc


def _parse_positive_int(name: str, raw: str) -> int:
    try:
        value = int(raw)
    except ValueError as exc:
        raise SettingsError(f"{name} must be an integer") from exc
    if value <= 0:
        raise SettingsError(f"{name} must be greater than zero")
    return value


def _optional_secret(raw: str | None) -> str | None:
    if raw is None:
        return None
    value = raw.strip()
    return value or None


def _normalize_database_url(raw: str) -> str:
    if raw.startswith("postgresql+asyncpg://"):
        return raw
    if raw.startswith("postgresql://"):
        return "postgresql+asyncpg://" + raw.removeprefix("postgresql://")
    if raw.startswith("postgres://"):
        return "postgresql+asyncpg://" + raw.removeprefix("postgres://")
    return raw
