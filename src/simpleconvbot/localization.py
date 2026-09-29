# Russian translations intentionally contain Cyrillic characters that Ruff's
# confusable-character rule flags by design in mixed-language source files.
# ruff: noqa: RUF001

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from simpleconvbot.jobs import JobState


class Locale(StrEnum):
    RU = "ru"
    EN = "en"


@dataclass(frozen=True, slots=True)
class LocalizedText:
    ru: str
    en: str

    def __post_init__(self) -> None:
        if not self.ru.strip() or not self.en.strip():
            raise ValueError("localized text must be non-empty in both languages")

    def get(self, locale: Locale) -> str:
        return self.ru if locale is Locale.RU else self.en


class UserErrorCode(StrEnum):
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    SESSION_NOT_FOUND = "session_not_found"
    SESSION_ACCESS_DENIED = "session_access_denied"
    SESSION_EXPIRED = "session_expired"
    SESSION_CLOSED = "session_closed"
    SESSION_EMPTY = "session_empty"
    SESSION_LIMIT_EXCEEDED = "session_limit_exceeded"
    SESSION_FILE_NOT_FOUND = "session_file_not_found"
    SESSION_IDEMPOTENCY_CONFLICT = "session_idempotency_conflict"
    SESSION_ALREADY_ACTIVE = "session_already_active"
    SESSION_WRONG_FILE_TYPE = "session_wrong_file_type"
    TELEGRAM_FILE_SIZE_UNKNOWN = "telegram_file_size_unknown"
    TELEGRAM_INPUT_TOO_LARGE = "telegram_input_too_large"
    TELEGRAM_DOWNLOAD_FAILED = "telegram_download_failed"
    TELEGRAM_UPLOAD_FAILED = "telegram_upload_failed"
    RESTART_INTERRUPTED = "restart_interrupted"
    INTERNAL_ERROR = "internal_error"


_OPERATION_TITLES: dict[str, LocalizedText] = {
    "image.to_jpeg": LocalizedText("Изображение → JPEG", "Image → JPEG"),
    "image.to_png": LocalizedText("Изображение → PNG", "Image → PNG"),
    "image.to_webp": LocalizedText("Изображение → WebP", "Image → WebP"),
    "image.compress": LocalizedText("Сжать изображение", "Compress image"),
    "image.resize": LocalizedText("Изменить размер изображения", "Resize image"),
    "pdf.to_images": LocalizedText("PDF → PNG-изображения", "PDF → PNG images"),
    "pdf.to_jpeg_images": LocalizedText("PDF → JPEG-изображения", "PDF → JPEG images"),
    "pdf.from_images": LocalizedText("Изображения → PDF", "Images → PDF"),
    "pdf.merge": LocalizedText("Объединить PDF", "Merge PDFs"),
    "pdf.extract_pages": LocalizedText("Извлечь страницы PDF", "Extract PDF pages"),
    "audio.to_mp3": LocalizedText("Аудио → MP3", "Audio → MP3"),
    "audio.to_m4a": LocalizedText("Аудио → M4A", "Audio → M4A"),
    "audio.to_wav": LocalizedText("Аудио → WAV", "Audio → WAV"),
    "video.to_mp3": LocalizedText("Видео → MP3", "Video → MP3"),
    "video.mute": LocalizedText("Убрать звук из видео", "Mute video"),
    "video.to_gif": LocalizedText("Видео → GIF", "Video → GIF"),
    "video.compress": LocalizedText("Сжать видео", "Compress video"),
}

_JOB_STATE_TEXT: dict[JobState, LocalizedText] = {
    JobState.RECEIVED: LocalizedText("Файл получен", "File received"),
    JobState.VALIDATING: LocalizedText("Проверяю файл", "Checking file"),
    JobState.QUEUED: LocalizedText("Задача в очереди", "Queued"),
    JobState.PROCESSING: LocalizedText("Обрабатываю файл", "Processing file"),
    JobState.UPLOADING: LocalizedText("Отправляю результат", "Sending result"),
    JobState.COMPLETED: LocalizedText("Готово", "Done"),
    JobState.REJECTED: LocalizedText("Файл отклонён", "File rejected"),
    JobState.FAILED: LocalizedText("Не удалось обработать файл", "Processing failed"),
    JobState.CANCELLED: LocalizedText("Операция отменена", "Operation cancelled"),
    JobState.EXPIRED: LocalizedText("Время операции истекло", "Operation expired"),
}

_ERROR_TEXT: dict[str, LocalizedText] = {
    # Image engine.
    "input_too_large": LocalizedText(
        "Изображение слишком большое для обработки.",
        "The image is too large to process.",
    ),
    "unsupported_type": LocalizedText(
        "Этот формат изображения пока не поддерживается.",
        "This image format is not supported yet.",
    ),
    "corrupt_input": LocalizedText(
        "Не удалось прочитать изображение. Возможно, файл повреждён.",
        "The image could not be read. The file may be damaged.",
    ),
    "dimensions_exceeded": LocalizedText(
        "Размеры изображения превышают допустимый предел.",
        "The image dimensions exceed the allowed limit.",
    ),
    "pixels_exceeded": LocalizedText(
        "Изображение содержит слишком много пикселей для безопасной обработки.",
        "The image has too many pixels for safe processing.",
    ),
    "multi_frame_unsupported": LocalizedText(
        "Анимированные и многостраничные изображения пока не поддерживаются.",
        "Animated and multi-frame images are not supported yet.",
    ),
    "invalid_parameters": LocalizedText(
        "Параметры операции недопустимы.",
        "The operation parameters are invalid.",
    ),
    "output_too_large": LocalizedText(
        "Результат получился слишком большим для отправки.",
        "The result is too large to send.",
    ),
    "output_validation_failed": LocalizedText(
        "Не удалось безопасно проверить готовый файл.",
        "The generated file could not be safely validated.",
    ),
    # PDF engine.
    "pdf_input_too_large": LocalizedText(
        "PDF слишком большой для обработки.",
        "The PDF is too large to process.",
    ),
    "pdf_aggregate_too_large": LocalizedText(
        "Общий размер выбранных файлов слишком большой.",
        "The selected files are too large in total.",
    ),
    "pdf_corrupt_input": LocalizedText(
        "Не удалось прочитать PDF. Возможно, файл повреждён.",
        "The PDF could not be read. The file may be damaged.",
    ),
    "pdf_encrypted_unsupported": LocalizedText(
        "PDF с паролем пока не поддерживаются.",
        "Password-protected PDFs are not supported yet.",
    ),
    "pdf_page_limit_exceeded": LocalizedText(
        "В PDF слишком много страниц для этой операции.",
        "The PDF has too many pages for this operation.",
    ),
    "pdf_page_dimensions_exceeded": LocalizedText(
        "Размер страницы PDF превышает допустимый предел.",
        "A PDF page exceeds the allowed dimensions.",
    ),
    "pdf_invalid_selection": LocalizedText(
        "Выбран недопустимый диапазон страниц.",
        "The selected page range is invalid.",
    ),
    "pdf_image_input_invalid": LocalizedText(
        "Один из файлов нельзя использовать для создания PDF.",
        "One of the files cannot be used to create a PDF.",
    ),
    "pdf_render_limit_exceeded": LocalizedText(
        "Страница PDF слишком большая для безопасного преобразования в изображение.",
        "A PDF page is too large to render safely.",
    ),
    "pdf_output_too_large": LocalizedText(
        "Готовый PDF получился слишком большим для отправки.",
        "The generated PDF is too large to send.",
    ),
    "pdf_output_validation_failed": LocalizedText(
        "Не удалось безопасно проверить готовый PDF.",
        "The generated PDF could not be safely validated.",
    ),
    "pdf_processing_failed": LocalizedText(
        "Не удалось обработать PDF.",
        "The PDF could not be processed.",
    ),
    # Media engine.
    "media_toolchain_unavailable": LocalizedText(
        "Обработка аудио и видео временно недоступна.",
        "Audio and video processing is temporarily unavailable.",
    ),
    "media_input_too_large": LocalizedText(
        "Медиафайл слишком большой для обработки.",
        "The media file is too large to process.",
    ),
    "media_corrupt_input": LocalizedText(
        "Не удалось прочитать медиафайл. Возможно, он повреждён.",
        "The media file could not be read. It may be damaged.",
    ),
    "media_unsupported_container": LocalizedText(
        "Этот формат контейнера пока не поддерживается.",
        "This media container is not supported yet.",
    ),
    "media_unsupported_codec": LocalizedText(
        "Этот аудио- или видеокодек пока не поддерживается.",
        "This audio or video codec is not supported yet.",
    ),
    "media_unsupported_streams": LocalizedText(
        "Структура этого медиафайла пока не поддерживается.",
        "This media stream layout is not supported yet.",
    ),
    "media_duration_limit_exceeded": LocalizedText(
        "Файл слишком длинный для этой операции.",
        "The file is too long for this operation.",
    ),
    "media_resolution_limit_exceeded": LocalizedText(
        "Разрешение видео превышает допустимый предел.",
        "The video resolution exceeds the allowed limit.",
    ),
    "media_invalid_operation": LocalizedText(
        "Эта операция для файла недоступна.",
        "This operation is not available for the file.",
    ),
    "media_timeout": LocalizedText(
        "Обработка заняла слишком много времени и была остановлена.",
        "Processing took too long and was stopped.",
    ),
    "media_output_too_large": LocalizedText(
        "Результат получился слишком большим для отправки.",
        "The result is too large to send.",
    ),
    "media_output_validation_failed": LocalizedText(
        "Не удалось безопасно проверить готовый медиафайл.",
        "The generated media file could not be safely validated.",
    ),
    "media_processing_failed": LocalizedText(
        "Не удалось обработать медиафайл.",
        "The media file could not be processed.",
    ),
    # Admission and abuse controls.
    "job_user_concurrency_limit": LocalizedText(
        "У вас уже выполняется слишком много операций. Дождитесь завершения одной из них.",
        "You already have too many active operations. Wait for one to finish.",
    ),
    "job_global_concurrency_limit": LocalizedText(
        "Сервис сейчас загружен. Попробуйте ещё раз немного позже.",
        "The service is busy right now. Please try again shortly.",
    ),
    "rate_limit_exceeded": LocalizedText(
        "Слишком много запросов. Попробуйте ещё раз немного позже.",
        "Too many requests. Please try again shortly.",
    ),
    # Collection sessions.
    "session_not_found": LocalizedText(
        "Сессия больше недоступна. Начните операцию заново.",
        "This session is no longer available. Start the operation again.",
    ),
    "session_access_denied": LocalizedText(
        "Эта сессия недоступна в текущем чате.",
        "This session is not available in the current chat.",
    ),
    "session_expired": LocalizedText(
        "Время сессии истекло. Начните операцию заново.",
        "The session expired. Start the operation again.",
    ),
    "session_closed": LocalizedText(
        "Эта сессия уже завершена.",
        "This session has already finished.",
    ),
    "session_empty": LocalizedText(
        "Сначала добавьте хотя бы один файл.",
        "Add at least one file first.",
    ),
    "session_limit_exceeded": LocalizedText(
        "Достигнут лимит файлов или их общего размера.",
        "The file-count or total-size limit has been reached.",
    ),
    "session_file_not_found": LocalizedText(
        "Файл не найден в текущей сессии.",
        "The file was not found in the current session.",
    ),
    "session_idempotency_conflict": LocalizedText(
        "Не удалось подтвердить повторную отправку файла. Начните операцию заново.",
        "The repeated file submission could not be verified. Start the operation again.",
    ),
    "session_already_active": LocalizedText(
        "Сначала завершите или отмените текущую сборку файлов.",
        "Finish or cancel the current file collection first.",
    ),
    "session_wrong_file_type": LocalizedText(
        "Для текущей сборки нужен другой тип файла.",
        "This collection expects a different file type.",
    ),
    "telegram_file_size_unknown": LocalizedText(
        "Telegram не сообщил размер файла, поэтому безопасно добавить его нельзя.",
        "Telegram did not provide the file size, so it cannot be added safely.",
    ),
    # Storage/sandbox codes are intentionally generalized for end users.
    "storage_invalid_internal_name": LocalizedText(
        "Не удалось подготовить временный файл.",
        "A temporary file could not be prepared.",
    ),
    "storage_root_symlink": LocalizedText(
        "Временное хранилище недоступно.",
        "Temporary storage is unavailable.",
    ),
    "storage_workspace_tampered": LocalizedText(
        "Временное хранилище не прошло проверку безопасности.",
        "Temporary storage failed a safety check.",
    ),
    "storage_unsupported_entry": LocalizedText(
        "Временный файл имеет недопустимый тип.",
        "A temporary file has an unsupported type.",
    ),
    "storage_quota_exceeded": LocalizedText(
        "Для этой операции превышен лимит временного места.",
        "This operation exceeded its temporary-storage limit.",
    ),
    "storage_cleanup_failed": LocalizedText(
        "Результат обработан, но очистка временных данных требует повторной проверки.",
        "Processing finished, but temporary-data cleanup needs another check.",
    ),
    "sandbox_unsupported_platform": LocalizedText(
        "Безопасная обработка этого файла сейчас недоступна.",
        "Safe processing for this file is currently unavailable.",
    ),
    "sandbox_invalid_workspace": LocalizedText(
        "Не удалось безопасно подготовить рабочее пространство.",
        "A safe workspace could not be prepared.",
    ),
    "sandbox_timeout": LocalizedText(
        "Обработка заняла слишком много времени и была остановлена.",
        "Processing took too long and was stopped.",
    ),
    "sandbox_child_failed": LocalizedText(
        "Изолированная обработка файла завершилась с ошибкой.",
        "Isolated file processing failed.",
    ),
    "sandbox_invalid_result": LocalizedText(
        "Результат изолированной обработки не прошёл проверку.",
        "The isolated processing result failed validation.",
    ),
    # Transport/internal fallback codes reserved for the Telegram adapter.
    "telegram_input_too_large": LocalizedText(
        "Файл слишком большой для загрузки в эту операцию.",
        "The file is too large to upload for this operation.",
    ),
    "telegram_download_failed": LocalizedText(
        "Не удалось получить файл из Telegram. Попробуйте отправить его ещё раз.",
        "The file could not be downloaded from Telegram. Please send it again.",
    ),
    "telegram_upload_failed": LocalizedText(
        "Не удалось отправить результат в Telegram. Попробуйте ещё раз позже.",
        "The result could not be sent to Telegram. Please try again later.",
    ),
    "restart_interrupted": LocalizedText(
        "Сервис перезапустился во время операции. "
        "Если результат не пришёл, отправьте файл ещё раз.",
        "The service restarted during the operation. "
        "If you did not receive the result, send the file again.",
    ),
    "internal_error": LocalizedText(
        "Произошла внутренняя ошибка. Попробуйте ещё раз позже.",
        "An internal error occurred. Please try again later.",
    ),
}

_UNKNOWN_ERROR = LocalizedText(
    "Не удалось выполнить операцию. Попробуйте ещё раз позже.",
    "The operation could not be completed. Please try again later.",
)


def resolve_locale(raw: str | None, *, default: Locale = Locale.RU) -> Locale:
    if raw is None:
        return default
    normalized = raw.strip().lower().replace("_", "-")
    if normalized == "ru" or normalized.startswith("ru-"):
        return Locale.RU
    if normalized == "en" or normalized.startswith("en-"):
        return Locale.EN
    return default


def operation_title(operation_id: str, locale: Locale) -> str:
    try:
        return _OPERATION_TITLES[operation_id].get(locale)
    except KeyError as exc:
        raise KeyError(f"unlocalized operation: {operation_id}") from exc


def job_state_text(state: JobState, locale: Locale) -> str:
    return _JOB_STATE_TEXT[state].get(locale)


def error_text(code: str, locale: Locale) -> str:
    message = _ERROR_TEXT.get(code, _UNKNOWN_ERROR)
    return message.get(locale)


def localized_operation_ids() -> frozenset[str]:
    return frozenset(_OPERATION_TITLES)


def localized_error_codes() -> frozenset[str]:
    return frozenset(_ERROR_TEXT)
