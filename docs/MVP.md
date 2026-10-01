# MVP Contract

This document defines the intended v0.1 scope. Changes to the supported matrix should be deliberate and reviewed.

## Single-file operations

### Images

Accepted inputs:

- JPEG
- PNG
- WEBP
- HEIC / HEIF when libheif support is available in the worker image

Initial operations:

- convert to JPEG
- convert to PNG
- convert to WEBP
- compress with safe presets
- resize by safe fixed presets: 25%, 50%, max 720 px, max 1080 px
- create a one-page PDF

Required metadata where available:

- actual MIME/type
- dimensions
- input size

The Telegram Image Info action must derive this metadata from decoded content rather than
the original filename extension or Telegram-supplied MIME type.

### PDF

Accepted input:

- valid PDF

Initial operations:

- render pages to images
- extract a bounded page/range selection
- split a PDF
- inspect page count
- lossless structural compression using fixed content-stream/object optimization; size reduction is not guaranteed and embedded images are not recompressed at lower quality

Multi-file operation:

- merge PDFs in user-selected order

### Audio

Accepted initial families:

- MP3
- M4A/AAC where supported by FFmpeg
- WAV

Initial operations:

- convert to MP3
- convert to M4A
- convert to WAV

### Video

Accepted initial families are determined by FFmpeg decoding capability, but the public UI should advertise common inputs such as MP4, MOV, and WEBM.

Initial operations:

- extract audio to MP3
- remove audio
- create GIF with bounded duration/resolution
- basic compression using named quality presets

No free-form codec or FFmpeg parameter entry is allowed.

## Multi-file sessions

v0.1 supports:

- multiple images -> one PDF
- multiple PDFs -> one merged PDF

A multi-file session must have a bounded lifetime and explicit maximum number and aggregate size of inputs.

## Preset design

The UI exposes understandable presets, not implementation parameters.

Examples:

Image compression:
- Best quality
- Balanced
- Smallest

Video compression:
- Best quality
- Balanced
- Smallest

Resize:
- 25%
- 50%
- max 720 px (no upscaling)
- max 1080 px (no upscaling)

Custom width/height input is deferred until operation parameters can be persisted
through the job model without weakening idempotency or restart recovery.

Internal numeric values belong to operation policy/configuration and can evolve without changing the public operation identity.

## Validation rules

Do not trust:

- filename extension
- user-supplied MIME type
- original filename
- dimensions reported without decoding/inspection

Validation must use actual content inspection and operation-specific bounds.

## Expected rejection classes

- unsupported type
- malformed/corrupt input
- file too large for current Telegram transport
- pixel/dimension limit exceeded
- PDF page limit exceeded
- multi-file aggregate limit exceeded
- operation output predicted or observed to exceed policy
- processing timeout
- unsupported codec
- temporary capacity unavailable

Each class should map to a stable internal error code and a human-readable user message.

## MVP release acceptance

v0.1 is releaseable only when:

- every advertised operation has golden-path integration coverage
- malformed input cannot crash the bot process
- workers have CPU, memory, disk, and time bounds
- duplicate Telegram delivery does not create duplicate jobs
- temporary input/output cleanup is verified
- output type is validated before sending
- user-facing failures are actionable
- unsupported files fail closed
- no user-provided value can become executable shell syntax
- secrets never appear in logs
- a restart does not silently mark unfinished jobs successful
- observability distinguishes validation, queue, worker, upload, and cleanup failures
