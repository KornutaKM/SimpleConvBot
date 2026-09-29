# RU/EN localization contract

ALPHA-001 requires Russian and English user-facing strings for the enabled conversion scope.

This module is deliberately independent from the current Telegram UI implementation so the parallel bot work can consume one stable catalog without this slice editing handlers or Railway runtime code.

## Covered operations

The catalog is keyed by the stable operation identity already used by the control plane:

- image.to_jpeg
- image.to_png
- image.to_webp
- image.compress
- image.resize
- pdf.to_images
- pdf.from_images
- pdf.merge
- pdf.extract_pages
- audio.to_mp3
- audio.to_m4a
- audio.to_wav
- video.to_mp3
- video.mute
- video.to_gif
- video.compress

A test compares this catalog to IMAGE_OPERATIONS, PDF_OPERATIONS and MEDIA_OPERATIONS exactly. Adding a new registered operation without localization therefore fails CI.

## Error messages

User-facing errors are selected by stable machine error code, never by exception text.

Coverage tests include every current value from:

- ImageErrorCode
- PdfErrorCode
- MediaErrorCode
- JobAdmissionCode
- StorageErrorCode
- SandboxErrorCode
- the Telegram/session adapter UserErrorCode set

Unknown error codes return one generic safe message. The unknown code itself is not interpolated into the message.

This prevents provider errors, paths, filenames, credentials or arbitrary parser text from leaking into routine Telegram responses.

## Job state

Every JobState has RU and EN status text, covering received, validation, queue, worker processing, upload and all terminal states.

## Locale resolution

Telegram-style language values such as ru-RU and en-US normalize to RU/EN. Missing or unsupported languages use an explicit default, currently Russian unless the caller chooses English.

## Integration rule

The Telegram implementation should pass only:

- stable operation_id
- stable error code
- JobState
- normalized locale

It should not build error text from raw exceptions.

The current legacy UI strings in ui.py remain untouched by this slice. When the parallel Telegram implementation is merged, it should migrate enabled workflow messages to this catalog rather than creating another translation source.
