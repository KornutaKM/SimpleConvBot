from __future__ import annotations

import logging
import re
from collections.abc import Iterable

_REDACTED = "<redacted>"
_PROVIDER_URL = re.compile(
    r"(?i)\b(?:postgres(?:ql)?(?:\+asyncpg)?|redis)://[^\s\"'<>]+"
)
_TELEGRAM_TOKEN = re.compile(r"\b[0-9]{5,}:[A-Za-z0-9_-]{20,}\b")
_AUTHORIZATION = re.compile(
    r"(?i)\bauthorization\s*[:=]\s*(?:bearer\s+)?[^\s,;]+"
)
_FILE_FIELD = re.compile(
    r"(?i)\b(?:file(?:_| )?path|file(?:_| )?name|filename)\s*[:=]\s*"
    r"(?:\"[^\"]*\"|'[^']*'|[^\s,;]+)"
)
_TELEGRAM_FILE_PATH = re.compile(
    r"(?i)\b(?:documents|photos|videos|audio|voice|animations|video_notes)/"
    r"[A-Za-z0-9_.-]+"
)


class RedactingFormatter(logging.Formatter):
    """Format a complete log record, then redact sensitive runtime material."""

    def __init__(
        self,
        fmt: str | None = None,
        *,
        sensitive_values: Iterable[str | None] = (),
    ) -> None:
        super().__init__(fmt)
        self._sensitive_values = tuple(
            sorted(
                {value for value in sensitive_values if value},
                key=len,
                reverse=True,
            )
        )

    def format(self, record: logging.LogRecord) -> str:
        rendered = super().format(record)
        return redact_log_text(rendered, sensitive_values=self._sensitive_values)


def redact_log_text(
    text: str,
    *,
    sensitive_values: Iterable[str | None] = (),
) -> str:
    rendered = text
    for value in sorted(
        {value for value in sensitive_values if value},
        key=len,
        reverse=True,
    ):
        rendered = rendered.replace(value, _REDACTED)

    rendered = _PROVIDER_URL.sub(_REDACTED, rendered)
    rendered = _TELEGRAM_TOKEN.sub(_REDACTED, rendered)
    rendered = _AUTHORIZATION.sub("authorization=<redacted>", rendered)
    rendered = _FILE_FIELD.sub("file=<redacted>", rendered)
    rendered = _TELEGRAM_FILE_PATH.sub(_REDACTED, rendered)
    return rendered


def configure_secure_logging(
    level: str,
    *,
    sensitive_values: Iterable[str | None] = (),
) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(
        RedactingFormatter(
            "%(levelname)s:%(name)s:%(message)s",
            sensitive_values=sensitive_values,
        )
    )
    logging.basicConfig(
        level=level,
        handlers=[handler],
        force=True,
    )
