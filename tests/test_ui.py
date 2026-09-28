from aiogram.types import InlineKeyboardMarkup

from simpleconvbot.ui import (
    CATEGORY_TITLES,
    HOME_CALLBACK,
    IMAGE_ACTION_TITLES,
    PDF_ACTION_TITLES,
    SEND_FILE_CALLBACK,
    SETTINGS_CALLBACK,
    TOOLS_CALLBACK,
    format_file_size,
    home_keyboard,
    image_actions_keyboard,
    image_document_card,
    pdf_actions_keyboard,
    tools_keyboard,
)


def _callback_data(markup: InlineKeyboardMarkup) -> set[str]:
    return {
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data is not None
    }


def test_home_keyboard_exposes_primary_navigation() -> None:
    assert _callback_data(home_keyboard()) == {
        SEND_FILE_CALLBACK,
        TOOLS_CALLBACK,
        SETTINGS_CALLBACK,
    }


def test_tools_keyboard_exposes_all_categories_and_back() -> None:
    callback_data = _callback_data(tools_keyboard())

    assert set(CATEGORY_TITLES) <= callback_data
    assert HOME_CALLBACK in callback_data


def test_image_action_keyboard_uses_fixed_callback_identities() -> None:
    callback_data = _callback_data(image_actions_keyboard())

    assert set(IMAGE_ACTION_TITLES) <= callback_data
    assert TOOLS_CALLBACK in callback_data
    assert all(len(value.encode("utf-8")) <= 64 for value in callback_data)


def test_pdf_action_keyboard_uses_fixed_callback_identities() -> None:
    callback_data = _callback_data(pdf_actions_keyboard())

    assert set(PDF_ACTION_TITLES) <= callback_data
    assert TOOLS_CALLBACK in callback_data
    assert all(len(value.encode("utf-8")) <= 64 for value in callback_data)


def test_file_size_formatting_is_compact() -> None:
    assert format_file_size(None) == "размер неизвестен"
    assert format_file_size(512) == "512 B"
    assert format_file_size(1536) == "1.5 KB"
    assert format_file_size(5 * 1024 * 1024) == "5.0 MB"


def test_user_supplied_filename_is_html_escaped() -> None:
    card = image_document_card("<b>unsafe.png</b>", "image/png", 10)

    assert "<b>unsafe.png</b>" not in card
    assert "&lt;b&gt;unsafe.png&lt;/b&gt;" in card
