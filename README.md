# SimpleConvBot

Telegram File Toolbox: send a file, choose an action, receive the result.

## Product status

Foundation / pre-MVP. The repository is being structured before implementation so that file processing, resource limits, privacy, and failure behavior are explicit contracts rather than implicit code behavior.

## Product promise

The happy path should be:

1. Send a supported file to the bot.
2. The bot detects what it is.
3. The bot shows only relevant actions.
4. The user starts an operation in at most two taps.
5. The bot returns a correct output file and deletes temporary data automatically.

No generative AI is required for the MVP.

## MVP scope

- Images: JPG, PNG, WEBP, HEIC; format conversion, compression, resize.
- PDF: images to PDF, PDF to images, merge, split/extract pages.
- Audio: MP3, M4A, WAV conversion.
- Video: extract audio, create GIF, mute, basic compression.
- Multi-file sessions: images to PDF and PDF merge.

See docs/MVP.md for the normative matrix.

## Architecture

Initial stack:

- Python
- aiogram
- FastAPI
- PostgreSQL
- Redis
- isolated workers
- FFmpeg / ffprobe
- Pillow and/or libvips
- libheif
- qpdf / MuPDF / Ghostscript where appropriate

The bot gateway never constructs arbitrary shell commands from user input. File operations are selected from a fixed operation registry and executed by bounded workers.

See docs/ARCHITECTURE.md and docs/SECURITY_PRIVACY.md.

## Telegram transport

Phase 1 uses the official Telegram Bot API. As of Bot API 10.3, the official API documents a 20 MB maximum file download and 50 MB multipart upload for general files. Telegram's self-hosted Local Bot API removes the download limit and supports uploads up to 2000 MB.

Large-file support is therefore a later transport upgrade, not a reason to complicate the first MVP.

Official reference: https://core.telegram.org/bots/api

## Product principles

- useful in seconds, without onboarding
- deterministic processing, not AI-generated output
- privacy by default
- temporary file storage only
- strict resource and abuse limits
- fail closed for unknown or malformed input
- idempotent handling of Telegram updates
- no hidden long-term file retention
- observability without logging sensitive filenames or file contents
- add features only after usage evidence

## Documentation

- docs/PRODUCT.md — product contract and success metrics
- docs/MVP.md — supported operations and acceptance criteria
- docs/ARCHITECTURE.md — system design and state machines
- docs/SECURITY_PRIVACY.md — threat model and privacy contract
- docs/ROADMAP.md — implementation sequence and release gates

## Working model

main is intended to remain reviewable and releasable. Substantial changes should arrive through focused branches and pull requests.
