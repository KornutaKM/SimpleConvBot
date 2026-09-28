from __future__ import annotations

from html import escape

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

HOME_CALLBACK = "ui:home"
SEND_FILE_CALLBACK = "ui:send-file"
TOOLS_CALLBACK = "ui:tools"
SETTINGS_CALLBACK = "ui:settings"

WELCOME_TEXT = (
    "⚡ <b>SimpleConv</b>\n\n"
    "Отправь файл, фото, видео, аудио, текст или число — "
    "я сам определю формат и покажу доступные действия."
)

TOOLS_TEXT = "🧰 <b>Все инструменты</b>\n\nВыберите категорию\nили просто отправьте файл."

SETTINGS_TEXT = "⚙️ <b>Настройки</b>\n\nПока здесь только параметры UI-прототипа."

IMAGE_CATEGORY_TEXT = "🖼 <b>Изображения</b>\n\nПопулярные действия:"
DOCUMENT_CATEGORY_TEXT = "📄 <b>Документы</b>\n\nПопулярные действия:"

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

IMAGE_ACTION_TITLES: dict[str, str] = {
    "ui:image:jpg": "JPG",
    "ui:image:webp": "WebP",
    "ui:image:pdf": "PDF",
    "ui:image:compress": "Сжатие",
    "ui:image:resize": "Изменение размера",
    "ui:image:crop": "Обрезка",
    "ui:image:exif": "Удаление EXIF",
    "ui:image:more": "Другие действия",
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


def _button(text: str, callback_data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=callback_data)


def home_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_button("📎 Отправить файл", SEND_FILE_CALLBACK)],
            [
                _button("🧰 Все инструменты", TOOLS_CALLBACK),
                _button("⚙️ Настройки", SETTINGS_CALLBACK),
            ],
        ]
    )


def tools_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _button("🖼 Изображения", "ui:cat:image"),
                _button("🎬 Видео", "ui:cat:video"),
            ],
            [
                _button("🎵 Аудио", "ui:cat:audio"),
                _button("📄 Документы", "ui:cat:document"),
            ],
            [
                _button("📦 Архивы", "ui:cat:archive"),
                _button("📊 Данные", "ui:cat:data"),
            ],
            [
                _button("📏 Единицы", "ui:cat:units"),
                _button("🔳 QR", "ui:cat:qr"),
            ],
            [
                _button("🔤 Текст", "ui:cat:text"),
                _button("🛠 Инструменты", "ui:cat:utils"),
            ],
            [_button("← Назад", HOME_CALLBACK)],
        ]
    )


def settings_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_button("🌐 Язык · Русский", "ui:setting:language")],
            [_button("🗑 Автоудаление · 1 час", "ui:setting:retention")],
            [_button("← Назад", HOME_CALLBACK)],
        ]
    )


def image_actions_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _button("JPG", "ui:image:jpg"),
                _button("WebP", "ui:image:webp"),
                _button("PDF", "ui:image:pdf"),
            ],
            [
                _button("🗜 Сжать", "ui:image:compress"),
                _button("📐 Размер", "ui:image:resize"),
            ],
            [
                _button("✂️ Обрезать", "ui:image:crop"),
                _button("🧹 EXIF", "ui:image:exif"),
            ],
            [_button("••• Ещё", "ui:image:more")],
            [_button("← Назад", TOOLS_CALLBACK)],
        ]
    )


def pdf_actions_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _button("🖼 → JPG", "ui:pdf:jpg"),
                _button("🖼 → PNG", "ui:pdf:png"),
            ],
            [
                _button("📑 Разделить", "ui:pdf:split"),
                _button("🧩 Объединить", "ui:pdf:merge"),
            ],
            [
                _button("🗜 Сжать", "ui:pdf:compress"),
                _button("🔍 Информация", "ui:pdf:info"),
            ],
            [_button("••• Ещё", "ui:pdf:more")],
            [_button("← Назад", TOOLS_CALLBACK)],
        ]
    )


def category_back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[_button("← Все инструменты", TOOLS_CALLBACK)]])


def image_back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[_button("← К изображениям", "ui:cat:image")]])


def pdf_back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[_button("← К документам", "ui:cat:document")]])


def format_file_size(size: int | None) -> str:
    if size is None:
        return "размер неизвестен"
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def photo_card(width: int, height: int, size: int | None) -> str:
    return (
        f"🖼 <b>Изображение</b>\n{width}×{height} • {format_file_size(size)}\n\n<b>Что сделать?</b>"
    )


def image_document_card(filename: str | None, mime_type: str | None, size: int | None) -> str:
    safe_name = escape(filename or "Изображение")
    safe_mime = escape(mime_type or "image")
    return f"🖼 <b>{safe_name}</b>\n{safe_mime} • {format_file_size(size)}\n\n<b>Что сделать?</b>"


def pdf_card(filename: str | None, size: int | None) -> str:
    safe_name = escape(filename or "document.pdf")
    return f"📄 <b>{safe_name}</b>\nPDF • {format_file_size(size)}\n\n<b>Что сделать?</b>"


def unsupported_document_card(
    filename: str | None,
    mime_type: str | None,
    size: int | None,
) -> str:
    safe_name = escape(filename or "Файл")
    safe_mime = escape(mime_type or "неизвестный формат")
    return (
        f"📎 <b>{safe_name}</b>\n"
        f"{safe_mime} • {format_file_size(size)}\n\n"
        "Для этого формата экран действий пока не подключён. "
        "Можно посмотреть доступные категории инструментов."
    )


def prototype_action_text(title: str) -> str:
    return (
        f"🚧 <b>{escape(title)}</b>\n\n"
        "Кнопка уже работает как часть Telegram-интерфейса. "
        "Сам движок преобразования подключим отдельным этапом."
    )


def category_placeholder_text(title: str) -> str:
    return (
        f"{escape(title)}\n\n"
        "Экран категории уже доступен в прототипе. "
        "Конкретные операции добавим по мере подключения движков."
    )
