from __future__ import annotations

import logging
import sys

from simpleconvbot.logging_security import RedactingFormatter, redact_log_text


def test_redact_log_text_removes_provider_urls_tokens_and_file_fields() -> None:
    token = "123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZ_abcd"
    database_url = "postgresql+asyncpg://user:db-secret@db.internal:5432/app"
    redis_url = "redis://default:redis-secret@cache.internal:6379/0"
    original_name = "passport-scan.pdf"
    telegram_path = "documents/file_42.pdf"

    rendered = redact_log_text(
        (
            f"token={token} db={database_url} redis={redis_url} "
            f"file_name={original_name} file_path={telegram_path} "
            "Authorization: Bearer external-secret"
        ),
        sensitive_values=(token, database_url, redis_url),
    )

    for forbidden in (
        token,
        database_url,
        redis_url,
        "db-secret",
        "redis-secret",
        original_name,
        telegram_path,
        "external-secret",
    ):
        assert forbidden not in rendered
    assert "<redacted>" in rendered


def test_redacting_formatter_scrubs_exception_traceback_text() -> None:
    token = "987654321:ABCDEFGHIJKLMNOPQRSTUVWXYZ_wxyz"
    database_url = "postgresql://user:secret-password@db.internal/app"
    formatter = RedactingFormatter(
        "%(levelname)s:%(name)s:%(message)s",
        sensitive_values=(token, database_url),
    )

    try:
        raise RuntimeError(
            f"provider failed at {database_url}; "
            f"file_path=photos/file_7.jpg; token={token}"
        )
    except RuntimeError:
        record = logging.LogRecord(
            name="simpleconvbot.test",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="operation failed",
            args=(),
            exc_info=sys.exc_info(),
        )

    rendered = formatter.format(record)

    assert "RuntimeError" in rendered
    assert "operation failed" in rendered
    assert token not in rendered
    assert database_url not in rendered
    assert "secret-password" not in rendered
    assert "photos/file_7.jpg" not in rendered
    assert "<redacted>" in rendered


def test_redacting_formatter_leaves_safe_structured_payload_readable() -> None:
    formatter = RedactingFormatter("%(levelname)s:%(name)s:%(message)s")
    record = logging.LogRecord(
        name="simpleconvbot.telemetry",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg='{"event":"operation_stage","operation_id":"image.to_png","outcome":"success"}',
        args=(),
        exc_info=None,
    )

    rendered = formatter.format(record)

    assert "operation_stage" in rendered
    assert "image.to_png" in rendered
    assert "success" in rendered
