from __future__ import annotations

import pytest

from simpleconvbot.image_engine import ImageErrorCode
from simpleconvbot.image_operations import IMAGE_OPERATIONS
from simpleconvbot.jobs import JobAdmissionCode, JobState
from simpleconvbot.localization import (
    Locale,
    UserErrorCode,
    error_text,
    job_state_text,
    localized_error_codes,
    localized_operation_ids,
    operation_title,
    resolve_locale,
)
from simpleconvbot.media_engine import MediaErrorCode
from simpleconvbot.media_operations import MEDIA_OPERATIONS
from simpleconvbot.pdf_engine import PdfErrorCode
from simpleconvbot.pdf_operations import PDF_OPERATIONS
from simpleconvbot.sandbox import SandboxErrorCode
from simpleconvbot.storage import StorageErrorCode


def test_every_registered_operation_has_ru_and_en_title() -> None:
    operation_ids = {
        operation.operation_id
        for operation in (*IMAGE_OPERATIONS, *PDF_OPERATIONS, *MEDIA_OPERATIONS)
    }

    assert localized_operation_ids() == operation_ids
    for operation_id in operation_ids:
        ru = operation_title(operation_id, Locale.RU)
        en = operation_title(operation_id, Locale.EN)
        assert ru.strip()
        assert en.strip()
        assert ru != en


def test_every_current_stable_error_enum_is_localized() -> None:
    expected = {
        *(code.value for code in ImageErrorCode),
        *(code.value for code in PdfErrorCode),
        *(code.value for code in MediaErrorCode),
        *(code.value for code in JobAdmissionCode),
        *(code.value for code in StorageErrorCode),
        *(code.value for code in SandboxErrorCode),
        *(code.value for code in UserErrorCode),
    }

    missing = expected - localized_error_codes()

    assert missing == set()
    for code in expected:
        assert error_text(code, Locale.RU).strip()
        assert error_text(code, Locale.EN).strip()


def test_every_job_state_has_ru_and_en_text() -> None:
    for state in JobState:
        ru = job_state_text(state, Locale.RU)
        en = job_state_text(state, Locale.EN)
        assert ru.strip()
        assert en.strip()


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("ru", Locale.RU),
        ("ru-RU", Locale.RU),
        ("RU_ru", Locale.RU),
        ("en", Locale.EN),
        ("en-US", Locale.EN),
        ("EN_gb", Locale.EN),
    ],
)
def test_locale_resolution_accepts_telegram_style_language_codes(
    raw: str,
    expected: Locale,
) -> None:
    assert resolve_locale(raw) is expected


def test_unknown_or_missing_locale_uses_explicit_default() -> None:
    assert resolve_locale(None) is Locale.RU
    assert resolve_locale("de-DE") is Locale.RU
    assert resolve_locale("de-DE", default=Locale.EN) is Locale.EN


def test_unknown_error_never_echoes_code_or_exception_detail() -> None:
    raw_code = "secret-provider-error-password-123"

    ru = error_text(raw_code, Locale.RU)
    en = error_text(raw_code, Locale.EN)

    assert raw_code not in ru
    assert raw_code not in en
    assert "password" not in ru.lower()
    assert "password" not in en.lower()


def test_unknown_operation_fails_closed() -> None:
    with pytest.raises(KeyError, match="unlocalized operation"):
        operation_title("future.operation", Locale.RU)
