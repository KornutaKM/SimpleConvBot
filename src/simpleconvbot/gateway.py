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

from simpleconvbot.localization import Locale, resolve_locale
from simpleconvbot.ports import UpdateReceiptStore
from simpleconvbot.sessions import SessionKind
from simpleconvbot.telegram_execution import (
    TelegramExecutionGateway,
    audio_operation,
    image_operation,
    pdf_operation,
    video_operation,
)
from simpleconvbot.telegram_sessions import TelegramCollectionGateway
from simpleconvbot.ui import (
    AUDIO_ACTION_TITLES,
    HOME_CALLBACK,
    IMAGE_ACTION_TITLES,
    PDF_ACTION_TITLES,
    SEND_FILE_CALLBACK,
    SETTINGS_CALLBACK,
    TOOLS_CALLBACK,
    VIDEO_ACTION_TITLES,
    action_title,
    audio_actions_keyboard,
    audio_card,
    category_back_keyboard,
    category_placeholder_text,
    category_text,
    category_title,
    home_keyboard,
    image_actions_keyboard,
    image_back_keyboard,
    image_document_card,
    message_unavailable_text,
    pdf_actions_keyboard,
    pdf_back_keyboard,
    pdf_card,
    photo_card,
    prototype_action_text,
    send_file_hint,
    session_unavailable_text,
    setting_notice_text,
    settings_keyboard,
    settings_text,
    source_unavailable_text,
    tools_keyboard,
    tools_text,
    unknown_category_text,
    unknown_operation_text,
    unsupported_document_card,
    video_actions_keyboard,
    video_card,
    welcome_text,
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


def _message_locale(message: Message) -> Locale:
    user = message.from_user
    return resolve_locale(user.language_code if user is not None else None)


def _callback_locale(callback: CallbackQuery) -> Locale:
    return resolve_locale(callback.from_user.language_code)


async def _edit_callback_message(
    callback: CallbackQuery,
    text: str,
    keyboard: InlineKeyboardMarkup,
    locale: Locale,
) -> None:
    message = callback.message
    if not isinstance(message, Message):
        await callback.answer(message_unavailable_text(locale), show_alert=True)
        return
    await message.edit_text(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
    await callback.answer()


async def _execute_callback(
    callback: CallbackQuery,
    execution: TelegramExecutionGateway | None,
    operation_id: str | None,
) -> None:
    locale = _callback_locale(callback)
    message = callback.message
    source = message.reply_to_message if isinstance(message, Message) else None
    if execution is None or not isinstance(source, Message) or operation_id is None:
        await callback.answer(source_unavailable_text(locale), show_alert=True)
        return
    await callback.answer()
    await execution.start_operation(source, operation_id, locale=locale)


async def _start_collection_callback(
    callback: CallbackQuery,
    collections: TelegramCollectionGateway | None,
    kind: SessionKind,
) -> None:
    locale = _callback_locale(callback)
    message = callback.message
    source = message.reply_to_message if isinstance(message, Message) else None
    if collections is None or not isinstance(source, Message):
        await callback.answer(source_unavailable_text(locale), show_alert=True)
        return
    await callback.answer()
    await collections.start(source, kind, locale=locale)


def create_router(
    execution: TelegramExecutionGateway | None = None,
    collections: TelegramCollectionGateway | None = None,
) -> Router:
    router = Router(name="simpleconvbot")

    @router.message(CommandStart())
    async def start(message: Message) -> None:
        locale = _message_locale(message)
        await message.answer(
            welcome_text(locale),
            reply_markup=home_keyboard(locale),
            parse_mode=ParseMode.HTML,
        )

    @router.message(Command("tools"))
    async def tools_command(message: Message) -> None:
        locale = _message_locale(message)
        await message.answer(
            tools_text(locale),
            reply_markup=tools_keyboard(locale),
            parse_mode=ParseMode.HTML,
        )

    @router.message(Command("settings"))
    async def settings_command(message: Message) -> None:
        locale = _message_locale(message)
        await message.answer(
            settings_text(locale),
            reply_markup=settings_keyboard(locale),
            parse_mode=ParseMode.HTML,
        )

    @router.callback_query(F.data == HOME_CALLBACK)
    async def home(callback: CallbackQuery) -> None:
        locale = _callback_locale(callback)
        await _edit_callback_message(
            callback,
            welcome_text(locale),
            home_keyboard(locale),
            locale,
        )

    @router.callback_query(F.data == SEND_FILE_CALLBACK)
    async def send_file(callback: CallbackQuery) -> None:
        await callback.answer(send_file_hint(_callback_locale(callback)), show_alert=True)

    @router.callback_query(F.data == TOOLS_CALLBACK)
    async def tools(callback: CallbackQuery) -> None:
        locale = _callback_locale(callback)
        await _edit_callback_message(
            callback,
            tools_text(locale),
            tools_keyboard(locale),
            locale,
        )

    @router.callback_query(F.data == SETTINGS_CALLBACK)
    async def settings(callback: CallbackQuery) -> None:
        locale = _callback_locale(callback)
        await _edit_callback_message(
            callback,
            settings_text(locale),
            settings_keyboard(locale),
            locale,
        )

    @router.callback_query(F.data.startswith("ui:setting:"))
    async def setting_placeholder(callback: CallbackQuery) -> None:
        await callback.answer(
            setting_notice_text(_callback_locale(callback), callback.data),
            show_alert=True,
        )

    @router.callback_query(F.data.startswith("ui:cat:"))
    async def category(callback: CallbackQuery) -> None:
        locale = _callback_locale(callback)
        callback_data = callback.data
        if callback_data is None:
            await callback.answer(unknown_category_text(locale), show_alert=True)
            return

        text = category_text(callback_data, locale)
        if callback_data == "ui:cat:image" and text is not None:
            await _edit_callback_message(
                callback,
                text,
                image_actions_keyboard(locale),
                locale,
            )
            return
        if callback_data == "ui:cat:document" and text is not None:
            await _edit_callback_message(
                callback,
                text,
                pdf_actions_keyboard(locale),
                locale,
            )
            return
        if callback_data == "ui:cat:audio" and text is not None:
            await _edit_callback_message(
                callback,
                text,
                audio_actions_keyboard(locale),
                locale,
            )
            return
        if callback_data == "ui:cat:video" and text is not None:
            await _edit_callback_message(
                callback,
                text,
                video_actions_keyboard(locale),
                locale,
            )
            return

        title = category_title(callback_data, locale)
        if title is None:
            await callback.answer(unknown_category_text(locale), show_alert=True)
            return
        await _edit_callback_message(
            callback,
            category_placeholder_text(title, locale),
            category_back_keyboard(locale),
            locale,
        )

    @router.callback_query(F.data == "ui:image:pdf")
    async def start_images_to_pdf(callback: CallbackQuery) -> None:
        await _start_collection_callback(
            callback,
            collections,
            SessionKind.IMAGES_TO_PDF,
        )

    @router.callback_query(
        F.data.in_({"ui:image:jpg", "ui:image:png", "ui:image:webp", "ui:image:compress"})
    )
    async def execute_image_action(callback: CallbackQuery) -> None:
        await _execute_callback(callback, execution, image_operation(callback.data))

    @router.callback_query(F.data == "ui:pdf:merge")
    async def start_pdf_merge(callback: CallbackQuery) -> None:
        await _start_collection_callback(
            callback,
            collections,
            SessionKind.PDF_MERGE,
        )

    @router.callback_query(F.data.in_({"ui:pdf:jpg", "ui:pdf:png", "ui:pdf:split"}))
    async def execute_pdf_action(callback: CallbackQuery) -> None:
        await _execute_callback(callback, execution, pdf_operation(callback.data))

    @router.callback_query(F.data.in_(set(AUDIO_ACTION_TITLES)))
    async def execute_audio_action(callback: CallbackQuery) -> None:
        await _execute_callback(callback, execution, audio_operation(callback.data))

    @router.callback_query(F.data.in_(set(VIDEO_ACTION_TITLES)))
    async def execute_video_action(callback: CallbackQuery) -> None:
        await _execute_callback(callback, execution, video_operation(callback.data))

    @router.callback_query(F.data.startswith("sess:"))
    async def collection_callback(callback: CallbackQuery) -> None:
        if collections is None:
            await callback.answer(
                session_unavailable_text(_callback_locale(callback)),
                show_alert=True,
            )
            return
        await collections.handle_callback(callback)

    @router.callback_query(F.data.startswith("ui:image:"))
    async def image_action(callback: CallbackQuery) -> None:
        locale = _callback_locale(callback)
        callback_data = callback.data
        if callback_data is None:
            await callback.answer(unknown_operation_text(locale), show_alert=True)
            return
        title = action_title(callback_data, locale)
        if title is None or callback_data not in IMAGE_ACTION_TITLES:
            await callback.answer(unknown_operation_text(locale), show_alert=True)
            return
        await _edit_callback_message(
            callback,
            prototype_action_text(title, locale),
            image_back_keyboard(locale),
            locale,
        )

    @router.callback_query(F.data.startswith("ui:pdf:"))
    async def pdf_action(callback: CallbackQuery) -> None:
        locale = _callback_locale(callback)
        callback_data = callback.data
        if callback_data is None:
            await callback.answer(unknown_operation_text(locale), show_alert=True)
            return
        title = action_title(callback_data, locale)
        if title is None or callback_data not in PDF_ACTION_TITLES:
            await callback.answer(unknown_operation_text(locale), show_alert=True)
            return
        await _edit_callback_message(
            callback,
            prototype_action_text(title, locale),
            pdf_back_keyboard(locale),
            locale,
        )

    @router.message(F.photo)
    async def photo_received(message: Message) -> None:
        if collections is not None and await collections.consume(message):
            return
        photos = message.photo
        if not photos:
            return
        locale = _message_locale(message)
        photo = photos[-1]
        await message.reply(
            photo_card(photo.width, photo.height, photo.file_size, locale),
            reply_markup=image_actions_keyboard(locale),
            parse_mode=ParseMode.HTML,
        )

    @router.message(F.audio)
    async def audio_received(message: Message) -> None:
        if collections is not None and await collections.consume(message):
            return
        audio = message.audio
        if audio is None:
            return
        locale = _message_locale(message)
        await message.reply(
            audio_card(audio.file_name, audio.file_size, locale),
            reply_markup=audio_actions_keyboard(locale),
            parse_mode=ParseMode.HTML,
        )

    @router.message(F.video)
    async def video_received(message: Message) -> None:
        if collections is not None and await collections.consume(message):
            return
        video = message.video
        if video is None:
            return
        locale = _message_locale(message)
        await message.reply(
            video_card(video.file_name, video.file_size, locale),
            reply_markup=video_actions_keyboard(locale),
            parse_mode=ParseMode.HTML,
        )

    @router.message(F.document)
    async def document_received(message: Message) -> None:
        if collections is not None and await collections.consume(message):
            return
        document = message.document
        if document is None:
            return

        locale = _message_locale(message)
        mime_type = document.mime_type
        if mime_type == "application/pdf":
            await message.reply(
                pdf_card(document.file_name, document.file_size, locale),
                reply_markup=pdf_actions_keyboard(locale),
                parse_mode=ParseMode.HTML,
            )
            return

        if mime_type is not None and mime_type.startswith("image/"):
            await message.reply(
                image_document_card(
                    document.file_name,
                    document.mime_type,
                    document.file_size,
                    locale,
                ),
                reply_markup=image_actions_keyboard(locale),
                parse_mode=ParseMode.HTML,
            )
            return

        if mime_type is not None and mime_type.startswith("audio/"):
            await message.reply(
                audio_card(document.file_name, document.file_size, locale),
                reply_markup=audio_actions_keyboard(locale),
                parse_mode=ParseMode.HTML,
            )
            return

        if mime_type is not None and mime_type.startswith("video/"):
            await message.reply(
                video_card(document.file_name, document.file_size, locale),
                reply_markup=video_actions_keyboard(locale),
                parse_mode=ParseMode.HTML,
            )
            return

        await message.answer(
            unsupported_document_card(
                document.file_name,
                document.mime_type,
                document.file_size,
                locale,
            ),
            reply_markup=tools_keyboard(locale),
            parse_mode=ParseMode.HTML,
        )

    return router


def create_dispatcher(
    receipts: UpdateReceiptStore,
    execution: TelegramExecutionGateway | None = None,
    collections: TelegramCollectionGateway | None = None,
) -> Dispatcher:
    dispatcher = Dispatcher()
    dispatcher.update.outer_middleware(UpdateDeduplicationMiddleware(receipts))
    dispatcher.include_router(create_router(execution, collections))
    return dispatcher
