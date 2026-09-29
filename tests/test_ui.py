from uuid import uuid4

from aiogram.types import InlineKeyboardMarkup

from simpleconvbot.localization import Locale
from simpleconvbot.ui import (
    AUDIO_ACTION_TITLES,
    CATEGORY_TITLES,
    HOME_CALLBACK,
    IMAGE_ACTION_TITLES,
    PDF_ACTION_TITLES,
    SEND_FILE_CALLBACK,
    SETTINGS_CALLBACK,
    TOOLS_CALLBACK,
    VIDEO_ACTION_TITLES,
    audio_actions_keyboard,
    collection_keyboard,
    format_file_size,
    home_keyboard,
    image_actions_keyboard,
    image_document_card,
    pdf_actions_keyboard,
    pdf_card,
    settings_text,
    send_file_hint,
    tools_keyboard,
    video_actions_keyboard,
    welcome_text,
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


def test_audio_action_keyboard_uses_fixed_callback_identities() -> None:
    callback_data = _callback_data(audio_actions_keyboard())

    assert set(AUDIO_ACTION_TITLES) <= callback_data
    assert TOOLS_CALLBACK in callback_data
    assert all(len(value.encode("utf-8")) <= 64 for value in callback_data)


def test_video_action_keyboard_uses_fixed_callback_identities() -> None:
    callback_data = _callback_data(video_actions_keyboard())

    assert set(VIDEO_ACTION_TITLES) <= callback_data
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


def test_collection_callbacks_fit_telegram_limit_and_bind_session() -> None:
    session_id = uuid4()
    callbacks = _callback_data(collection_keyboard(session_id))

    assert callbacks == {
        f"sess:add:{session_id}",
        f"sess:done:{session_id}",
        f"sess:cancel:{session_id}",
    }
    assert all(len(value.encode("utf-8")) <= 64 for value in callbacks)


def _button_text(markup: InlineKeyboardMarkup) -> set[str]:
    return {button.text for row in markup.inline_keyboard for button in row}


def test_english_ui_is_real_not_catalog_only() -> None:
    assert "Send a file, photo, video, or audio" in welcome_text(Locale.EN)
    assert "interface follows your Telegram language" in settings_text(Locale.EN)
    assert "What would you like to do?" in pdf_card("sample.pdf", 1024, Locale.EN)
    assert "📎 How to send a file" in _button_text(home_keyboard(Locale.EN))
    assert "🧰 All tools" in _button_text(home_keyboard(Locale.EN))
    assert "← Back" in _button_text(audio_actions_keyboard(Locale.EN))


def test_russian_remains_default_for_existing_clients() -> None:
    assert "Отправьте файл, фото, видео или аудио" in welcome_text(Locale.RU)
    assert "Что сделать?" in pdf_card("sample.pdf", 1024, Locale.RU)
    assert "📎 Как отправить файл" in _button_text(home_keyboard())


def test_send_file_hint_is_explicit_about_telegram_attachment_control() -> None:
    assert "скрепку Telegram" in send_file_hint(Locale.RU)
    assert "file, photo, video, or audio" in send_file_hint(Locale.EN)
