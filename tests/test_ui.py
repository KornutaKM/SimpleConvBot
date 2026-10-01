from uuid import uuid4

from aiogram.types import InlineKeyboardMarkup

from simpleconvbot.image_engine import ImageFormat, ImageInfo
from simpleconvbot.localization import Locale
from simpleconvbot.ui import (
    AUDIO_ACTION_TITLES,
    HELP_CALLBACK,
    HOME_CALLBACK,
    SEND_FILE_CALLBACK,
    SETTINGS_CALLBACK,
    TOOLS_CALLBACK,
    VIDEO_ACTION_TITLES,
    audio_actions_keyboard,
    collection_keyboard,
    format_file_size,
    help_keyboard,
    help_text,
    home_keyboard,
    image_actions_keyboard,
    image_compress_keyboard,
    image_compress_text,
    image_document_card,
    image_info_text,
    image_resize_keyboard,
    image_resize_text,
    pdf_actions_keyboard,
    pdf_card,
    pdf_info_text,
    send_file_hint,
    settings_text,
    tools_keyboard,
    video_actions_keyboard,
    video_compress_keyboard,
    video_compress_text,
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
        HELP_CALLBACK,
    }


def test_tools_keyboard_exposes_only_enabled_alpha_categories_and_back() -> None:
    callback_data = _callback_data(tools_keyboard())

    assert callback_data == {
        "ui:cat:image",
        "ui:cat:video",
        "ui:cat:audio",
        "ui:cat:document",
        HOME_CALLBACK,
    }


def test_image_action_keyboard_exposes_only_enabled_alpha_operations() -> None:
    callback_data = _callback_data(image_actions_keyboard())

    assert callback_data == {
        "ui:image:jpg",
        "ui:image:png",
        "ui:image:webp",
        "ui:image:pdf",
        "ui:image:compress",
        "ui:image:resize",
        "ui:image:info",
        TOOLS_CALLBACK,
    }
    assert all(len(value.encode("utf-8")) <= 64 for value in callback_data)


def test_image_info_text_uses_content_metadata_in_both_locales() -> None:
    info = ImageInfo(
        image_format=ImageFormat.PNG,
        width=32,
        height=16,
        mode="RGBA",
        has_alpha=True,
        byte_size=1536,
    )

    ru = image_info_text(info, Locale.RU)
    en = image_info_text(info, Locale.EN)

    assert "PNG" in ru and "image/png" in ru
    assert "32×16 px" in ru
    assert "1.5 KB" in ru
    assert "RGBA" in ru
    assert "Прозрачность: <b>да</b>" in ru
    assert "PNG" in en and "image/png" in en
    assert "32×16 px" in en
    assert "1.5 KB" in en
    assert "RGBA" in en
    assert "Alpha: <b>yes</b>" in en


def test_compression_keyboard_exposes_named_presets_and_back() -> None:
    callback_data = _callback_data(image_compress_keyboard(Locale.EN))

    assert callback_data == {
        "ui:image:compress:best",
        "ui:image:compress:balanced",
        "ui:image:compress:smallest",
        "ui:image:compress:back",
    }
    assert "best quality" in image_compress_text(Locale.EN)
    assert "лучшее качество" in image_compress_text(Locale.RU)
    assert all(len(value.encode("utf-8")) <= 64 for value in callback_data)


def test_resize_keyboard_exposes_only_safe_presets_and_back() -> None:
    callback_data = _callback_data(image_resize_keyboard(Locale.EN))

    assert callback_data == {
        "ui:image:resize:25",
        "ui:image:resize:50",
        "ui:image:resize:720",
        "ui:image:resize:1080",
        "ui:image:resize:back",
    }
    assert "do not upscale" in image_resize_text(Locale.EN)
    assert "не увеличивают" in image_resize_text(Locale.RU)
    assert all(len(value.encode("utf-8")) <= 64 for value in callback_data)


def test_pdf_action_keyboard_exposes_only_enabled_alpha_operations() -> None:
    callback_data = _callback_data(pdf_actions_keyboard())

    assert callback_data == {
        "ui:pdf:jpg",
        "ui:pdf:png",
        "ui:pdf:split",
        "ui:pdf:merge",
        "ui:pdf:compress",
        "ui:pdf:info",
        TOOLS_CALLBACK,
    }
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


def test_video_compression_keyboard_exposes_named_presets_and_back() -> None:
    callback_data = _callback_data(video_compress_keyboard(Locale.EN))

    assert callback_data == {
        "ui:video:compress:best",
        "ui:video:compress:balanced",
        "ui:video:compress:smallest",
        "ui:video:compress:back",
    }
    assert "best quality" in video_compress_text(Locale.EN)
    assert "лучшее качество" in video_compress_text(Locale.RU)
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
    assert "📎 Send a file" in _button_text(home_keyboard(Locale.EN))
    assert "🧰 All tools" in _button_text(home_keyboard(Locale.EN))
    assert "← Back" in _button_text(audio_actions_keyboard(Locale.EN))


def test_russian_remains_default_for_existing_clients() -> None:
    assert "Отправьте файл, фото, видео или аудио" in welcome_text(Locale.RU)
    assert "Что сделать?" in pdf_card("sample.pdf", 1024, Locale.RU)
    assert "📎 Отправить файл" in _button_text(home_keyboard())


def test_send_file_hint_is_explicit_about_telegram_attachment_control() -> None:
    assert "скрепку Telegram" in send_file_hint(Locale.RU)
    assert "file, photo, video, or audio" in send_file_hint(Locale.EN)


def test_pdf_info_text_is_localized_and_uses_existing_size_formatting() -> None:
    ru = pdf_info_text(3, 1536, "1.7", Locale.RU)
    en = pdf_info_text(3, 1536, "1.7", Locale.EN)

    assert "Страниц: 3" in ru
    assert "Размер: 1.5 KB" in ru
    assert "Версия: 1.7" in ru
    assert "Pages: 3" in en
    assert "Size: 1.5 KB" in en
    assert "Version: 1.7" in en


def test_help_surface_is_ru_en_symmetric_and_returns_home() -> None:
    ru = help_text(Locale.RU)
    en = help_text(Locale.EN)

    assert "Как пользоваться" in ru
    assert "How to use SimpleConv" in en
    assert "до 20 файлов" in ru
    assert "up to 20 files" in en
    assert "до 40 МБ" in ru
    assert "up to 40 MB" in en
    assert "одного входного файла — до 20 МБ" in ru
    assert "each input file is limited to 20 MB" in en
    assert "через 1 час" in ru
    assert "after 1 hour" in en
    assert "скрепку Telegram" in ru
    assert "Telegram attachment button" in en
    assert "изменение размера" in ru
    assert "resize" in en
    assert "сжатие с пресетами" in ru
    assert "compression presets" in en
    assert "фактический формат и размеры" in ru
    assert "actual format and dimensions" in en
    assert "сжатие без потери качества" in ru
    assert "lossless compression" in en
    assert "не гарантирует уменьшение" in ru
    assert "does not guarantee" in en
    assert _callback_data(help_keyboard(Locale.RU)) == {HOME_CALLBACK}
    assert _callback_data(help_keyboard(Locale.EN)) == {HOME_CALLBACK}


def test_home_keyboard_exposes_localized_help_button() -> None:
    assert "❓ Помощь" in _button_text(home_keyboard(Locale.RU))
    assert "❓ Help" in _button_text(home_keyboard(Locale.EN))
