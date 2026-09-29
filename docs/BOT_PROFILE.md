# Telegram public bot profile

This is the canonical public-profile contract for the first SimpleConvBot
release. Repository presence does not prove that Telegram currently shows these
values.

Official Telegram references:

- https://core.telegram.org/bots/api
- https://core.telegram.org/bots/features

## Canonical identity

Fallback/global display name:

```text
SimpleConv
```

Russian display name:

```text
SimpleConv
```

The in-bot product brand is also `SimpleConv`. Applying this contract therefore
removes the alpha-era display-name drift if Telegram currently shows a different
name.

The Telegram username is not changed by the repository tool. Keep the existing
username unless the operator deliberately changes it in Telegram.

## Fallback / English profile

Short description:

```text
File converter for images, PDF, audio and video — right inside Telegram.
```

Description:

```text
Convert images, PDF, audio and video in Telegram. Supports JPG/PNG/WebP, images → PDF, PDF → JPG/PNG, split/merge, MP3/M4A/WAV, video → MP3/GIF, mute and compression. Standard Bot API input limit: 20 MB. Temporary files are deleted automatically after 1 hour. Privacy: https://github.com/KornutaKM/SimpleConvBot/blob/main/docs/PRIVACY.md
```

## Russian profile

Short description:

```text
Конвертер изображений, PDF, аудио и видео прямо в Telegram.
```

Description:

```text
Конвертируйте изображения, PDF, аудио и видео прямо в Telegram. JPG/PNG/WebP, изображения → PDF, PDF → JPG/PNG, разделение/объединение, MP3/M4A/WAV, видео → MP3/GIF, без звука и сжатие. Лимит одного входного файла через стандартный Bot API: 20 МБ. Временные файлы автоматически удаляются через 1 час. Конфиденциальность: https://github.com/KornutaKM/SimpleConvBot/blob/main/docs/PRIVACY.md
```

The source of truth for these strings is
`src/simpleconvbot/bot_profile.py`; tests enforce Telegram's current name,
short-description, and description limits.

## Commands

The application owns the command menu at runtime. Do not maintain a competing
manual command list in BotFather.

Fallback:

```text
/start    Home
/tools    All tools
/help     Help
/settings Settings
```

Russian (`language_code=ru`):

```text
/start    Главный экран
/tools    Все инструменты
/help     Помощь
/settings Настройки
```

These are registered by `src/simpleconvbot/runtime.py` after startup health
checks pass and the singleton runtime lease is owned.

## Review without changing Telegram

From an installed project environment:

```bash
python scripts/bot_profile.py
```

This is a dry run. It prints the canonical plan and performs no Telegram API
mutation. No token is required.

## Explicit apply

Only after the operator confirms that the reviewed values should become public:

```bash
export TELEGRAM_BOT_TOKEN="<secret>"
python scripts/bot_profile.py --apply
```

On Windows PowerShell:

```powershell
$env:TELEGRAM_BOT_TOKEN = "<secret>"
python scripts/bot_profile.py --apply
Remove-Item Env:TELEGRAM_BOT_TOKEN
```

Do not paste the token into GitHub issues, screenshots, documentation, shell
history intended for sharing, or chat evidence.

The apply tool updates the fallback and Russian name, short description, and
description. It does not alter the username, avatar, or commands.

## Avatar

The avatar is an external operator gate. Telegram recommends a distinctive,
high-quality bot image.

Use the already approved SimpleConv bot artwork if the operator has it. Do not
substitute an unreviewed image just to close the release gate. After publishing,
capture only non-sensitive evidence that the intended avatar is visible.

## Verification evidence

After applying the profile, verify from Telegram itself:

1. open the bot profile with an English/non-Russian Telegram locale;
2. confirm name, short description, full description and privacy URL;
3. repeat with Russian locale;
4. confirm the avatar;
5. open the command menu and confirm the four fallback/RU commands;
6. confirm the username still targets the intended production bot;
7. record the verification timestamp and bot username without recording the bot
   token.

Only then may the BotFather/public-profile item in
`docs/RELEASE_CHECKLIST.md` be marked complete.
