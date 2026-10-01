# SimpleConvBot

Telegram File Toolbox: send a file, choose an action, receive the result.

## Product status

Private alpha is complete with RU/EN manual coverage and all runtime evidence gates satisfied. Repository-side public-readiness controls are implemented, and Railway is the selected first production hosting path. Public launch remains blocked on real provider deployment/operator evidence in `docs/RELEASE_CHECKLIST.md`.

## Product promise

The happy path should be:

1. Send a supported file to the bot.
2. The bot detects what it is.
3. The bot shows only relevant actions.
4. The user starts an operation in at most two taps.
5. The bot returns a correct output file and deletes temporary data automatically.

No generative AI is required for the MVP.

## MVP scope

- Images: JPG, PNG, WEBP, HEIC; format conversion, named compression presets, safe resize presets (25%, 50%, max 720/1080 px), actual image metadata.
- PDF: images to PDF, PDF to images, merge, split/extract pages, lossless structural compression.
- Audio: MP3, M4A, WAV conversion.
- Video: extract audio, create GIF, mute, named compression presets.
- Multi-file sessions: images to PDF and PDF merge, with add/remove-last/finalize controls.

See docs/MVP.md for the normative matrix.

## Architecture

Initial stack:

- Python
- aiogram
- PostgreSQL
- Redis
- isolated/bounded conversion workers
- FFmpeg / ffprobe
- Pillow and/or libvips
- libheif
- qpdf / MuPDF / Ghostscript where appropriate

The bot gateway never constructs arbitrary shell commands from user input. File operations are selected from a fixed operation registry and executed by bounded workers.

See docs/ARCHITECTURE.md and docs/SECURITY_PRIVACY.md.

## Local validation runtime

The completed private-alpha runtime is reproducible locally; a remote host was not required for ALPHA-001.

For the reproducible Docker path:

1. Copy `.env.example` to `.env`.
2. Set `TELEGRAM_BOT_TOKEN` and a local PostgreSQL password.
3. Run:

   ```bash
   docker compose --profile bot up --build
   ```

This starts exactly one bot application together with PostgreSQL and Redis. See
`docs/DEPLOYMENT.md` for host-Python mode, evidence capture, restart behavior,
and the Telegram end-to-end checklist.

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
- docs/SECURITY_PRIVACY.md — threat model and security/privacy contract
- docs/PRIVACY.md — public MVP privacy notice
- docs/BOT_PROFILE.md — canonical Telegram public profile and safe apply procedure
- docs/RETENTION.md — file/session/metadata retention contract
- docs/PRODUCTION.md — public production, monitoring, smoke, and rollback runbook
- docs/RAILWAY.md — first-release Railway deployment contract and evidence procedure
- docs/RELEASE_CHECKLIST.md — RELEASE-001 repository and external gates
- docs/ROADMAP.md — implementation sequence and release gates
- docs/DEPLOYMENT.md — completed local private-alpha runbook
- docs/PRIVATE_ALPHA.md — completed alpha evidence checklist

## Working model

main is intended to remain reviewable and releasable. Substantial changes should arrive through focused branches and pull requests.
