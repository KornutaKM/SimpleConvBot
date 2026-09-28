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
    redis_url: str = "redis://localhost:6379/0"
    temp_root: Path = Path("var/jobs")
    temp_ttl_seconds: int = 3600

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

        return cls(
            environment=environment,
            log_level=log_level,
            telegram_bot_token=_optional_secret(values.get("TELEGRAM_BOT_TOKEN")),
            database_url=values.get(
                "DATABASE_URL",
                "postgresql+asyncpg://simpleconvbot@localhost:5432/simpleconvbot",
            ).strip(),
            redis_url=values.get("REDIS_URL", "redis://localhost:6379/0").strip(),
            temp_root=Path(values.get("TEMP_ROOT", "var/jobs")).expanduser(),
            temp_ttl_seconds=temp_ttl_seconds,
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
