from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware, Dispatcher, F, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardMarkup,
    Message,
    TelegramObject,
    Update,
)

from simpleconvbot.ports import UpdateReceiptStore
from simpleconvbot.telegram_execution import (
    TelegramExecutionGateway,
    audio_operation,
    image_operation,
    pdf_operation,
    video_operation,
)
from simpleconvbot.ui import (
    AUDIO_ACTION_TITLES,
    AUDIO_CATEGORY_TEXT,
    CATEGORY_TITLES,
    DOCUMENT_CATEGORY_TEXT,
    HOME_CALLBACK,
    IMAGE_ACTION_TITLES,
    IMAGE_CATEGORY_TEXT,
    PDF_ACTION_TITLES,
    SEND_FILE_CALLBACK,
    SETTINGS_CALLBACK,
    SETTINGS_TEXT,
    TOOLS_CALLBACK,
    TOOLS_TEXT,
    VIDEO_ACTION_TITLES,
    VIDEO_CATEGORY_TEXT,
    WELCOME_TEXT,
    audio_actions_keyboard,
    audio_card,
    category_back_keyboard,
    category_placeholder_text,
    home_keyboard,
    image_actions_keyboard,
    image_back_keyboard,
    image_document_card,
    pdf_actions_keyboard,
    pdf_back_keyboard,
    pdf_card,
    photo_card,
    prototype_action_text,
    settings_keyboard,
    tools_keyboard,
    unsupported_document_card,
    video_actions_keyboard,
    video_card,
)

Handler = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]


class UpdateDeduplicationMiddleware(BaseMiddleware):
    def __init__(self, receipts: UpdateReceiptStore) -> None:
        self._receipts = receipts

    async def __call__(
        self,
        handler: Handler,
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, Update) and not await self._receipts.claim(event.update_id):
            return None
        return await handler(event, data)


async def _edit_callback_message(
    callback: CallbackQuery,
    text: str,
    keyboard: InlineKeyboardMarkup,
) -> None:
    message = callback.message
    if not isinstance(message, Message):
        await callback.answer("Сообщение больше недоступно.", show_alert=True)
        return
    await message.edit_text(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
    await callback.answer()


async def _execute_callback(
    callback: CallbackQuery,
    execution: TelegramExecutionGateway | None,
    operation_id: str | None,
) -> None:
    message = callback.message
    source = message.reply_to_message if isinstance(message, Message) else None
    if execution is None or not isinstance(source, Message) or operation_id is None:
        await callback.answer("Файл больше недоступен. Отправьте его ещё раз.", show_alert=True)
        return
    await callback.answer()
    await execution.start_operation(source, operation_id)


def create_router(execution: TelegramExecutionGateway | None = None) -> Router:
    router = Router(name="simpleconvbot")

    @router.message(CommandStart())
    async def start(message: Message) -> None:
        await message.answer(
            WELCOME_TEXT,
            reply_markup=home_keyboard(),
            parse_mode=ParseMode.HTML,
        )

    @router.message(Command("tools"))
    async def tools_command(message: Message) -> None:
        await message.answer(
            TOOLS_TEXT,
            reply_markup=tools_keyboard(),
            parse_mode=ParseMode.HTML,
        )

    @router.message(Command("settings"))
    async def settings_command(message: Message) -> None:
        await message.answer(
            SETTINGS_TEXT,
            reply_markup=settings_keyboard(),
            parse_mode=ParseMode.HTML,
        )

    @router.callback_query(F.data == HOME_CALLBACK)
    async def home(callback: CallbackQuery) -> None:
        await _edit_callback_message(callback, WELCOME_TEXT, home_keyboard())

    @router.callback_query(F.data == SEND_FILE_CALLBACK)
    async def send_file(callback: CallbackQuery) -> None:
        await callback.answer(
            "Нажмите скрепку Telegram рядом с полем сообщения и выберите файл.",
            show_alert=True,
        )

    @router.callback_query(F.data == TOOLS_CALLBACK)
    async def tools(callback: CallbackQuery) -> None:
        await _edit_callback_message(callback, TOOLS_TEXT, tools_keyboard())

    @router.callback_query(F.data == SETTINGS_CALLBACK)
    async def settings(callback: CallbackQuery) -> None:
        await _edit_callback_message(callback, SETTINGS_TEXT, settings_keyboard())

    @router.callback_query(F.data.startswith("ui:setting:"))
    async def setting_placeholder(callback: CallbackQuery) -> None:
        await callback.answer("Параметр пока работает как элемент UI-прототипа.")

    @router.callback_query(F.data.startswith("ui:cat:"))
    async def category(callback: CallbackQuery) -> None:
        callback_data = callback.data
        if callback_data is None:
            await callback.answer("Неизвестная категория.", show_alert=True)
            return

        if callback_data == "ui:cat:image":
            await _edit_callback_message(
                callback,
                IMAGE_CATEGORY_TEXT,
                image_actions_keyboard(),
            )
            return
        if callback_data == "ui:cat:document":
            await _edit_callback_message(
                callback,
                DOCUMENT_CATEGORY_TEXT,
                pdf_actions_keyboard(),
            )
            return
        if callback_data == "ui:cat:audio":
            await _edit_callback_message(
                callback,
                AUDIO_CATEGORY_TEXT,
                audio_actions_keyboard(),
            )
            return
        if callback_data == "ui:cat:video":
            await _edit_callback_message(
                callback,
                VIDEO_CATEGORY_TEXT,
                video_actions_keyboard(),
            )
            return

        title = CATEGORY_TITLES.get(callback_data)
        if title is None:
            await callback.answer("Неизвестная категория.", show_alert=True)
            return
        await _edit_callback_message(
            callback,
            category_placeholder_text(title),
            category_back_keyboard(),
        )

    @router.callback_query(
        F.data.in_({"ui:image:jpg", "ui:image:png", "ui:image:webp", "ui:image:compress"})
    )
    async def execute_image_action(callback: CallbackQuery) -> None:
        await _execute_callback(callback, execution, image_operation(callback.data))

    @router.callback_query(F.data == "ui:pdf:png")
    async def execute_pdf_action(callback: CallbackQuery) -> None:
        await _execute_callback(callback, execution, pdf_operation(callback.data))

    @router.callback_query(F.data.in_(set(AUDIO_ACTION_TITLES)))
    async def execute_audio_action(callback: CallbackQuery) -> None:
        await _execute_callback(callback, execution, audio_operation(callback.data))

    @router.callback_query(F.data.in_(set(VIDEO_ACTION_TITLES)))
    async def execute_video_action(callback: CallbackQuery) -> None:
        await _execute_callback(callback, execution, video_operation(callback.data))

    @router.callback_query(F.data.startswith("ui:image:"))
    async def image_action(callback: CallbackQuery) -> None:
        callback_data = callback.data
        if callback_data is None:
            await callback.answer("Неизвестная операция.", show_alert=True)
            return
        title = IMAGE_ACTION_TITLES.get(callback_data)
        if title is None:
            await callback.answer("Неизвестная операция.", show_alert=True)
            return
        await _edit_callback_message(
            callback,
            prototype_action_text(title),
            image_back_keyboard(),
        )

    @router.callback_query(F.data.startswith("ui:pdf:"))
    async def pdf_action(callback: CallbackQuery) -> None:
        callback_data = callback.data
        if callback_data is None:
            await callback.answer("Неизвестная операция.", show_alert=True)
            return
        title = PDF_ACTION_TITLES.get(callback_data)
        if title is None:
            await callback.answer("Неизвестная операция.", show_alert=True)
            return
        await _edit_callback_message(
            callback,
            prototype_action_text(title),
            pdf_back_keyboard(),
        )

    @router.message(F.photo)
    async def photo_received(message: Message) -> None:
        photos = message.photo
        if not photos:
            return
        photo = photos[-1]
        await message.reply(
            photo_card(photo.width, photo.height, photo.file_size),
            reply_markup=image_actions_keyboard(),
            parse_mode=ParseMode.HTML,
        )

    @router.message(F.audio)
    async def audio_received(message: Message) -> None:
        audio = message.audio
        if audio is None:
            return
        await message.reply(
            audio_card(audio.file_name, audio.file_size),
            reply_markup=audio_actions_keyboard(),
            parse_mode=ParseMode.HTML,
        )

    @router.message(F.video)
    async def video_received(message: Message) -> None:
        video = message.video
        if video is None:
            return
        await message.reply(
            video_card(video.file_name, video.file_size),
            reply_markup=video_actions_keyboard(),
            parse_mode=ParseMode.HTML,
        )

    @router.message(F.document)
    async def document_received(message: Message) -> None:
        document = message.document
        if document is None:
            return

        mime_type = document.mime_type
        if mime_type == "application/pdf":
            await message.reply(
                pdf_card(document.file_name, document.file_size),
                reply_markup=pdf_actions_keyboard(),
                parse_mode=ParseMode.HTML,
            )
            return

        if mime_type is not None and mime_type.startswith("image/"):
            await message.reply(
                image_document_card(
                    document.file_name,
                    document.mime_type,
                    document.file_size,
                ),
                reply_markup=image_actions_keyboard(),
                parse_mode=ParseMode.HTML,
            )
            return

        if mime_type is not None and mime_type.startswith("audio/"):
            await message.reply(
                audio_card(document.file_name, document.file_size),
                reply_markup=audio_actions_keyboard(),
                parse_mode=ParseMode.HTML,
            )
            return

        if mime_type is not None and mime_type.startswith("video/"):
            await message.reply(
                video_card(document.file_name, document.file_size),
                reply_markup=video_actions_keyboard(),
                parse_mode=ParseMode.HTML,
            )
            return

        await message.answer(
            unsupported_document_card(
                document.file_name,
                document.mime_type,
                document.file_size,
            ),
            reply_markup=tools_keyboard(),
            parse_mode=ParseMode.HTML,
        )

    return router


def create_dispatcher(
    receipts: UpdateReceiptStore,
    execution: TelegramExecutionGateway | None = None,
) -> Dispatcher:
    dispatcher = Dispatcher()
    dispatcher.update.outer_middleware(UpdateDeduplicationMiddleware(receipts))
    dispatcher.include_router(create_router(execution))
    return dispatcher
