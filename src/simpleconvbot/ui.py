from __future__ import annotations

from html import escape
from uuid import UUID

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from simpleconvbot.localization import Locale
from simpleconvbot.sessions import CollectionSessionSnapshot, SessionKind

HOME_CALLBACK = "ui:home"
SEND_FILE_CALLBACK = "ui:send-file"
TOOLS_CALLBACK = "ui:tools"
SETTINGS_CALLBACK = "ui:settings"
HELP_CALLBACK = "ui:help"

WELCOME_TEXT = (
    "⚡ <b>SimpleConv</b>\n\n"
    "Отправьте файл, фото, видео или аудио — "
    "я определю формат и покажу доступные действия."
)
TOOLS_TEXT = "🧰 <b>Все инструменты</b>\n\nВыберите категорию\nили просто отправьте файл."
SETTINGS_TEXT = "⚙️ <b>Настройки</b>\n\nЯзык интерфейса определяется языком Telegram."
IMAGE_CATEGORY_TEXT = "🖼 <b>Изображения</b>\n\nПопулярные действия:"
DOCUMENT_CATEGORY_TEXT = "📄 <b>Документы</b>\n\nПопулярные действия:"
AUDIO_CATEGORY_TEXT = "🎵 <b>Аудио</b>\n\nДоступные преобразования:"
VIDEO_CATEGORY_TEXT = "🎬 <b>Видео</b>\n\nДоступные преобразования:"

CATEGORY_TITLES: dict[str, str] = {
    "ui:cat:image": "🖼 Изображения",
    "ui:cat:video": "🎬 Видео",
    "ui:cat:audio": "🎵 Аудио",
    "ui:cat:document": "📄 Документы",
    "ui:cat:archive": "📦 Архивы",
    "ui:cat:data": "📊 Данные",
    "ui:cat:units": "📏 Единицы",
    "ui:cat:qr": "🔳 QR",
    "ui:cat:text": "🔤 Текст",
    "ui:cat:utils": "🛠 Инструменты",
}
_CATEGORY_EN = {
    "ui:cat:image": "🖼 Images",
    "ui:cat:video": "🎬 Video",
    "ui:cat:audio": "🎵 Audio",
    "ui:cat:document": "📄 Documents",
    "ui:cat:archive": "📦 Archives",
    "ui:cat:data": "📊 Data",
    "ui:cat:units": "📏 Units",
    "ui:cat:qr": "🔳 QR",
    "ui:cat:text": "🔤 Text",
    "ui:cat:utils": "🛠 Utilities",
}

IMAGE_ACTION_TITLES: dict[str, str] = {
    "ui:image:jpg": "JPG",
    "ui:image:png": "PNG",
    "ui:image:webp": "WebP",
    "ui:image:pdf": "PDF",
    "ui:image:compress": "Сжатие",
    "ui:image:resize": "Изменение размера",
    "ui:image:crop": "Обрезка",
    "ui:image:exif": "Удаление EXIF",
    "ui:image:more": "Другие действия",
}
_IMAGE_ACTION_EN = {
    "ui:image:jpg": "JPG",
    "ui:image:png": "PNG",
    "ui:image:webp": "WebP",
    "ui:image:pdf": "PDF",
    "ui:image:compress": "Compress",
    "ui:image:resize": "Resize",
    "ui:image:crop": "Crop",
    "ui:image:exif": "Remove EXIF",
    "ui:image:more": "More actions",
}

PDF_ACTION_TITLES: dict[str, str] = {
    "ui:pdf:jpg": "PDF → JPG",
    "ui:pdf:png": "PDF → PNG",
    "ui:pdf:split": "Разделить PDF",
    "ui:pdf:merge": "Объединить PDF",
    "ui:pdf:compress": "Сжать PDF",
    "ui:pdf:info": "Информация о PDF",
    "ui:pdf:more": "Другие действия",
}
_PDF_ACTION_EN = {
    "ui:pdf:jpg": "PDF → JPG",
    "ui:pdf:png": "PDF → PNG",
    "ui:pdf:split": "Split PDF",
    "ui:pdf:merge": "Merge PDFs",
    "ui:pdf:compress": "Compress PDF",
    "ui:pdf:info": "PDF info",
    "ui:pdf:more": "More actions",
}

AUDIO_ACTION_TITLES: dict[str, str] = {
    "ui:audio:mp3": "MP3",
    "ui:audio:m4a": "M4A",
    "ui:audio:wav": "WAV",
}
_AUDIO_ACTION_EN = AUDIO_ACTION_TITLES

VIDEO_ACTION_TITLES: dict[str, str] = {
    "ui:video:mp3": "Извлечь MP3",
    "ui:video:mute": "Убрать звук",
    "ui:video:gif": "GIF",
    "ui:video:compress": "Сжать",
}
_VIDEO_ACTION_EN = {
    "ui:video:mp3": "Extract MP3",
    "ui:video:mute": "Mute",
    "ui:video:gif": "GIF",
    "ui:video:compress": "Compress",
}


def _pick(locale: Locale, ru: str, en: str) -> str:
    return ru if locale is Locale.RU else en


def welcome_text(locale: Locale) -> str:
    return _pick(
        locale,
        WELCOME_TEXT,
        (
            "⚡ <b>SimpleConv</b>\n\n"
            "Send a file, photo, video, or audio — "
            "I’ll detect the format and show the available actions."
        ),
    )


def tools_text(locale: Locale) -> str:
    return _pick(
        locale,
        TOOLS_TEXT,
        "🧰 <b>All tools</b>\n\nChoose a category\nor just send a file.",
    )


def settings_text(locale: Locale) -> str:
    return _pick(
        locale,
        SETTINGS_TEXT,
        "⚙️ <b>Settings</b>\n\nThe interface follows your Telegram language.",
    )


def help_text(locale: Locale) -> str:
    return _pick(
        locale,
        (
            "❓ <b>Помощь</b>\n\n"
            "<b>Как пользоваться</b>\n"
            "1. Нажмите скрепку Telegram и отправьте файл, фото, видео или аудио.\n"
            "2. Выберите действие.\n"
            "3. Дождитесь готового результата.\n\n"
            "<b>Что умеет SimpleConv</b>\n"
            "🖼 Изображения: JPG, PNG, WebP, сжатие, изображения → PDF.\n"
            "📄 PDF: JPG, PNG, разделение, объединение, информация о PDF.\n"
            "🎵 Аудио: MP3, M4A, WAV.\n"
            "🎬 Видео: MP3, без звука, GIF, сжатие.\n\n"
            "<b>Несколько файлов</b>\n"
            "Для «Изображения → PDF» и «Объединить PDF» можно добавить до 20 файлов "
            "общим размером до 40 МБ, затем нажать «Готово». "
            "При стандартном Telegram Bot API размер одного входного файла — до 20 МБ.\n\n"
            "<b>Хранение и ошибки</b>\n"
            "Временные данные автоматически удаляются через 1 час. "
            "Если формат не поддерживается, файл слишком большой или повреждён, "
            "бот покажет понятное сообщение и не будет продолжать небезопасную обработку."
        ),
        (
            "❓ <b>Help</b>\n\n"
            "<b>How to use SimpleConv</b>\n"
            "1. Tap the Telegram attachment button and send a file, photo, video, or audio.\n"
            "2. Choose an action.\n"
            "3. Wait for the converted result.\n\n"
            "<b>What SimpleConv can do</b>\n"
            "🖼 Images: JPG, PNG, WebP, compression, images → PDF.\n"
            "📄 PDF: JPG, PNG, split, merge, PDF information.\n"
            "🎵 Audio: MP3, M4A, WAV.\n"
            "🎬 Video: MP3, mute, GIF, compression.\n\n"
            "<b>Multiple files</b>\n"
            "For Images → PDF and Merge PDFs, add up to 20 files with a total size "
            "of up to 40 MB, then tap “Done”. "
            "With the standard Telegram Bot API, each input file is limited to 20 MB.\n\n"
            "<b>Storage and errors</b>\n"
            "Temporary data is deleted automatically after 1 hour. "
            "If a format is unsupported, a file is too large, or a file is damaged, "
            "the bot shows a clear error instead of continuing unsafe processing."
        ),
    )


def category_text(callback_data: str, locale: Locale) -> str | None:
    values = {
        "ui:cat:image": _pick(
            locale,
            IMAGE_CATEGORY_TEXT,
            "🖼 <b>Images</b>\n\nPopular actions:",
        ),
        "ui:cat:document": _pick(
            locale,
            DOCUMENT_CATEGORY_TEXT,
            "📄 <b>Documents</b>\n\nPopular actions:",
        ),
        "ui:cat:audio": _pick(
            locale,
            AUDIO_CATEGORY_TEXT,
            "🎵 <b>Audio</b>\n\nAvailable conversions:",
        ),
        "ui:cat:video": _pick(
            locale,
            VIDEO_CATEGORY_TEXT,
            "🎬 <b>Video</b>\n\nAvailable conversions:",
        ),
    }
    return values.get(callback_data)


def category_title(callback_data: str, locale: Locale) -> str | None:
    return (CATEGORY_TITLES if locale is Locale.RU else _CATEGORY_EN).get(callback_data)


def action_title(callback_data: str, locale: Locale) -> str | None:
    groups = (
        (IMAGE_ACTION_TITLES, _IMAGE_ACTION_EN),
        (PDF_ACTION_TITLES, _PDF_ACTION_EN),
        (AUDIO_ACTION_TITLES, _AUDIO_ACTION_EN),
        (VIDEO_ACTION_TITLES, _VIDEO_ACTION_EN),
    )
    for ru, en in groups:
        if callback_data in ru:
            return (ru if locale is Locale.RU else en)[callback_data]
    return None


def _button(text: str, callback_data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=callback_data)


def home_keyboard(locale: Locale = Locale.RU) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _button(
                    _pick(locale, "📎 Отправить файл", "📎 Send a file"),
                    SEND_FILE_CALLBACK,
                )
            ],
            [
                _button(
                    _pick(locale, "🧰 Все инструменты", "🧰 All tools"),
                    TOOLS_CALLBACK,
                ),
                _button(
                    _pick(locale, "❓ Помощь", "❓ Help"),
                    HELP_CALLBACK,
                ),
            ],
            [
                _button(
                    _pick(locale, "⚙️ Настройки", "⚙️ Settings"),
                    SETTINGS_CALLBACK,
                )
            ],
        ]
    )


def tools_keyboard(locale: Locale = Locale.RU) -> InlineKeyboardMarkup:
    titles = CATEGORY_TITLES if locale is Locale.RU else _CATEGORY_EN
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _button(titles["ui:cat:image"], "ui:cat:image"),
                _button(titles["ui:cat:video"], "ui:cat:video"),
            ],
            [
                _button(titles["ui:cat:audio"], "ui:cat:audio"),
                _button(titles["ui:cat:document"], "ui:cat:document"),
            ],
            [_button(_pick(locale, "← Назад", "← Back"), HOME_CALLBACK)],
        ]
    )


def settings_keyboard(locale: Locale = Locale.RU) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _button(
                    _pick(locale, "🌐 Язык · Telegram", "🌐 Language · Telegram"),
                    "ui:setting:language",
                )
            ],
            [
                _button(
                    _pick(
                        locale,
                        "🗑 Автоудаление · 1 час",
                        "🗑 Auto-delete · 1 hour",
                    ),
                    "ui:setting:retention",
                )
            ],
            [_button(_pick(locale, "← Назад", "← Back"), HOME_CALLBACK)],
        ]
    )


def help_keyboard(locale: Locale = Locale.RU) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_button(_pick(locale, "← Назад", "← Back"), HOME_CALLBACK)],
        ]
    )


def image_actions_keyboard(locale: Locale = Locale.RU) -> InlineKeyboardMarkup:
    titles = IMAGE_ACTION_TITLES if locale is Locale.RU else _IMAGE_ACTION_EN
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _button("JPG", "ui:image:jpg"),
                _button("PNG", "ui:image:png"),
                _button("WebP", "ui:image:webp"),
                _button("PDF", "ui:image:pdf"),
            ],
            [_button(f"🗜 {titles['ui:image:compress']}", "ui:image:compress")],
            [_button(_pick(locale, "← Назад", "← Back"), TOOLS_CALLBACK)],
        ]
    )


def pdf_actions_keyboard(locale: Locale = Locale.RU) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_button("🖼 → JPG", "ui:pdf:jpg"), _button("🖼 → PNG", "ui:pdf:png")],
            [
                _button(
                    _pick(locale, "📑 Разделить", "📑 Split"),
                    "ui:pdf:split",
                ),
                _button(
                    _pick(locale, "🧩 Объединить", "🧩 Merge"),
                    "ui:pdf:merge",
                ),
            ],
            [_button(f"🔍 {_pick(locale, 'Информация', 'Info')}", "ui:pdf:info")],
            [_button(_pick(locale, "← Назад", "← Back"), TOOLS_CALLBACK)],
        ]
    )


def audio_actions_keyboard(locale: Locale = Locale.RU) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _button("MP3", "ui:audio:mp3"),
                _button("M4A", "ui:audio:m4a"),
                _button("WAV", "ui:audio:wav"),
            ],
            [_button(_pick(locale, "← Назад", "← Back"), TOOLS_CALLBACK)],
        ]
    )


def video_actions_keyboard(locale: Locale = Locale.RU) -> InlineKeyboardMarkup:
    titles = VIDEO_ACTION_TITLES if locale is Locale.RU else _VIDEO_ACTION_EN
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _button("🎵 MP3", "ui:video:mp3"),
                _button(f"🔇 {titles['ui:video:mute']}", "ui:video:mute"),
            ],
            [
                _button("🎞 GIF", "ui:video:gif"),
                _button(f"🗜 {titles['ui:video:compress']}", "ui:video:compress"),
            ],
            [_button(_pick(locale, "← Назад", "← Back"), TOOLS_CALLBACK)],
        ]
    )


def collection_keyboard(
    session_id: UUID,
    locale: Locale = Locale.RU,
) -> InlineKeyboardMarkup:
    raw = str(session_id)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _button(
                    _pick(locale, "➕ Добавить файл", "➕ Add file"),
                    f"sess:add:{raw}",
                )
            ],
            [
                _button(_pick(locale, "✅ Готово", "✅ Done"), f"sess:done:{raw}"),
                _button(_pick(locale, "✖️ Отмена", "✖️ Cancel"), f"sess:cancel:{raw}"),
            ],
        ]
    )


def collection_status_text(
    snapshot: CollectionSessionSnapshot,
    locale: Locale = Locale.RU,
) -> str:
    if locale is Locale.RU:
        title = (
            "🖼 <b>Изображения → PDF</b>"
            if snapshot.kind is SessionKind.IMAGES_TO_PDF
            else "🧩 <b>Объединение PDF</b>"
        )
        noun = "файл" if snapshot.file_count == 1 else "файлов"
        return (
            f"{title}\n\n"
            f"Добавлено: <b>{snapshot.file_count}</b> {noun}\n"
            f"Общий размер: <b>{format_file_size(snapshot.total_bytes, locale)}</b>\n\n"
            "Отправьте следующий файл или нажмите «Готово»."
        )
    title = (
        "🖼 <b>Images → PDF</b>"
        if snapshot.kind is SessionKind.IMAGES_TO_PDF
        else "🧩 <b>Merge PDFs</b>"
    )
    noun = "file" if snapshot.file_count == 1 else "files"
    return (
        f"{title}\n\n"
        f"Added: <b>{snapshot.file_count}</b> {noun}\n"
        f"Total size: <b>{format_file_size(snapshot.total_bytes, locale)}</b>\n\n"
        "Send the next file or tap “Done”."
    )


def category_back_keyboard(locale: Locale = Locale.RU) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_button(_pick(locale, "← Все инструменты", "← All tools"), TOOLS_CALLBACK)]
        ]
    )


def image_back_keyboard(locale: Locale = Locale.RU) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[_button(_pick(locale, "← К изображениям", "← Images"), "ui:cat:image")]]
    )


def pdf_back_keyboard(locale: Locale = Locale.RU) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_button(_pick(locale, "← К документам", "← Documents"), "ui:cat:document")]
        ]
    )


def format_file_size(size: int | None, locale: Locale = Locale.RU) -> str:
    if size is None:
        return _pick(locale, "размер неизвестен", "size unknown")
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def photo_card(
    width: int,
    height: int,
    size: int | None,
    locale: Locale = Locale.RU,
) -> str:
    return (
        f"🖼 <b>{_pick(locale, 'Изображение', 'Image')}</b>\n"
        f"{width}×{height} • {format_file_size(size, locale)}\n\n"
        f"<b>{_pick(locale, 'Что сделать?', 'What would you like to do?')}</b>"
    )


def image_document_card(
    filename: str | None,
    mime_type: str | None,
    size: int | None,
    locale: Locale = Locale.RU,
) -> str:
    safe_name = escape(filename or _pick(locale, "Изображение", "Image"))
    safe_mime = escape(mime_type or "image")
    return (
        f"🖼 <b>{safe_name}</b>\n{safe_mime} • {format_file_size(size, locale)}\n\n"
        f"<b>{_pick(locale, 'Что сделать?', 'What would you like to do?')}</b>"
    )


def pdf_card(filename: str | None, size: int | None, locale: Locale = Locale.RU) -> str:
    safe_name = escape(filename or "document.pdf")
    return (
        f"📄 <b>{safe_name}</b>\nPDF • {format_file_size(size, locale)}\n\n"
        f"<b>{_pick(locale, 'Что сделать?', 'What would you like to do?')}</b>"
    )


def pdf_info_text(
    page_count: int,
    size: int,
    version: str,
    locale: Locale = Locale.RU,
) -> str:
    return (
        f"📄 PDF\n"
        f"{_pick(locale, 'Страниц', 'Pages')}: {page_count}\n"
        f"{_pick(locale, 'Размер', 'Size')}: {format_file_size(size, locale)}\n"
        f"{_pick(locale, 'Версия', 'Version')}: {escape(version)}"
    )


def audio_card(
    filename: str | None,
    size: int | None,
    locale: Locale = Locale.RU,
) -> str:
    safe_name = escape(filename or _pick(locale, "Аудиофайл", "Audio file"))
    return (
        f"🎵 <b>{safe_name}</b>\n{format_file_size(size, locale)}\n\n"
        f"<b>{_pick(locale, 'Что сделать?', 'What would you like to do?')}</b>"
    )


def video_card(
    filename: str | None,
    size: int | None,
    locale: Locale = Locale.RU,
) -> str:
    safe_name = escape(filename or _pick(locale, "Видео", "Video"))
    return (
        f"🎬 <b>{safe_name}</b>\n{format_file_size(size, locale)}\n\n"
        f"<b>{_pick(locale, 'Что сделать?', 'What would you like to do?')}</b>"
    )


def unsupported_document_card(
    filename: str | None,
    mime_type: str | None,
    size: int | None,
    locale: Locale = Locale.RU,
) -> str:
    safe_name = escape(filename or _pick(locale, "Файл", "File"))
    safe_mime = escape(mime_type or _pick(locale, "неизвестный формат", "unknown format"))
    body = _pick(
        locale,
        (
            "Для этого формата экран действий пока не подключён. "
            "Можно посмотреть доступные категории инструментов."
        ),
        (
            "Actions for this format are not available yet. "
            "You can browse the available tool categories."
        ),
    )
    return f"📎 <b>{safe_name}</b>\n{safe_mime} • {format_file_size(size, locale)}\n\n{body}"


def prototype_action_text(title: str, locale: Locale = Locale.RU) -> str:
    body = _pick(
        locale,
        "Эта операция пока не подключена к Telegram-потоку.",
        "This operation is not connected to the Telegram flow yet.",
    )
    return f"🚧 <b>{escape(title)}</b>\n\n{body}"


def category_placeholder_text(title: str, locale: Locale = Locale.RU) -> str:
    body = _pick(
        locale,
        "Категория доступна, но конкретные операции пока не подключены.",
        "This category is available, but its operations are not connected yet.",
    )
    return f"{escape(title)}\n\n{body}"


def message_unavailable_text(locale: Locale) -> str:
    return _pick(
        locale,
        "Сообщение больше недоступно.",
        "This message is no longer available.",
    )


def source_unavailable_text(locale: Locale) -> str:
    return _pick(
        locale,
        "Файл больше недоступен. Отправьте его ещё раз.",
        "The file is no longer available. Please send it again.",
    )


def send_file_hint(locale: Locale) -> str:
    return _pick(
        locale,
        (
            "Чтобы отправить файл, нажмите скрепку Telegram рядом с полем сообщения "
            "и выберите файл, фото, видео или аудио."
        ),
        (
            "To send a file, tap the Telegram attachment button next to the message field "
            "and choose a file, photo, video, or audio."
        ),
    )


def setting_notice_text(locale: Locale, setting: str | None) -> str:
    if setting == "ui:setting:language":
        return _pick(
            locale,
            ("SimpleConv автоматически использует язык вашего Telegram: русский или английский."),
            ("SimpleConv automatically follows your Telegram language: Russian or English."),
        )
    return _pick(
        locale,
        "Автоудаление временных данных настроено на 1 час.",
        "Temporary data is automatically deleted after 1 hour.",
    )


def unknown_category_text(locale: Locale) -> str:
    return _pick(locale, "Неизвестная категория.", "Unknown category.")


def unknown_operation_text(locale: Locale) -> str:
    return _pick(locale, "Неизвестная операция.", "Unknown operation.")


def session_unavailable_text(locale: Locale) -> str:
    return _pick(
        locale,
        "Сессия временно недоступна.",
        "The session is temporarily unavailable.",
    )


def session_add_hint(locale: Locale) -> str:
    return _pick(
        locale,
        "Отправьте следующий файл в этот чат.",
        "Send the next file to this chat.",
    )


def session_cancelled_text(locale: Locale) -> str:
    return _pick(locale, "Сборка файлов отменена.", "File collection cancelled.")


def operation_accepted_text(locale: Locale) -> str:
    return _pick(
        locale,
        "Принято. Начинаю обработку файла.",
        "Accepted. Processing has started.",
    )


def operation_duplicate_text(locale: Locale) -> str:
    return _pick(
        locale,
        "Эта операция уже принята к обработке.",
        "This operation has already been accepted for processing.",
    )


def collection_accepted_text(title: str, locale: Locale) -> str:
    return _pick(
        locale,
        f"{title}: принято в обработку.",
        f"{title}: accepted for processing.",
    )


def collection_duplicate_text(locale: Locale) -> str:
    return _pick(
        locale,
        "Эта сборка уже принята к обработке.",
        "This collection has already been accepted for processing.",
    )
