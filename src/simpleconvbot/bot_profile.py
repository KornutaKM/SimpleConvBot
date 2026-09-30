from __future__ import annotations

from dataclasses import dataclass

PRIVACY_URL = "https://github.com/KornutaKM/SimpleConvBot/blob/main/docs/PRIVACY.md"


@dataclass(frozen=True, slots=True)
class BotProfile:
    language_code: str
    name: str
    short_description: str
    description: str


DEFAULT_PROFILE = BotProfile(
    language_code="",
    name="SimpleConv",
    short_description="File converter for images, PDF, audio and video — right inside Telegram.",
    description=(
        "Convert images, PDF, audio and video in Telegram. "
        "Supports JPG/PNG/WebP, images → PDF, PDF → JPG/PNG, split/merge, "
        "MP3/M4A/WAV, video → MP3/GIF, mute and compression. "
        "Standard Bot API input limit: 20 MB. "
        "Temporary files are deleted automatically after 1 hour. "
        f"Privacy: {PRIVACY_URL}"
    ),
)

RU_PROFILE = BotProfile(
    language_code="ru",
    name="SimpleConv",
    short_description="Конвертер изображений, PDF, аудио и видео прямо в Telegram.",
    description=(
        "Конвертируйте изображения, PDF, аудио и видео прямо в Telegram. "
        "JPG/PNG/WebP, изображения → PDF, PDF → JPG/PNG, разделение/объединение, "
        "MP3/M4A/WAV, видео → MP3/GIF, без звука и сжатие. "
        "Лимит одного входного файла через стандартный Bot API: 20 МБ. "
        "Временные файлы автоматически удаляются через 1 час. "
        f"Конфиденциальность: {PRIVACY_URL}"
    ),
)

PUBLIC_PROFILES = (DEFAULT_PROFILE, RU_PROFILE)
