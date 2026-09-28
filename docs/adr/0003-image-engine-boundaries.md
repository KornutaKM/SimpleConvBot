# ADR 0003 — Content-based bounded image engine

Status: Accepted

## Context

Image files are untrusted input. Extensions and client MIME values can be spoofed, compressed images can expand to very large pixel buffers, and source images can contain privacy-sensitive metadata or multiple frames.

The image engine must also remain independent of Telegram so it can be tested deterministically and later executed inside an isolated worker.

## Decision

- Use Pillow 12.3.0 for JPEG/PNG/WEBP decoding and encoding.
- Use pillow-heif 1.8.0 to register HEIF/HEIC support with Pillow.
- Detect actual format using decoder/content inspection, never extension alone.
- Apply explicit input-byte, width, height, pixel-count, and output-byte bounds.
- Promote Pillow decompression-bomb warnings and errors to failures.
- Limit HEIF decoding to one decoder thread per operation; worker-level concurrency controls aggregate CPU use.
- Reject multi-frame inputs in the initial image MVP.
- Apply EXIF orientation before transformation.
- Do not propagate arbitrary EXIF/XMP metadata to outputs.
- Preserve alpha for PNG/WEBP; composite onto white for JPEG.
- Expose named compression presets rather than raw encoder controls.
- Keep the engine API independent of Telegram transport and filenames.

## Consequences

Positive:

- extension spoofing cannot select a decoder path
- user input cannot choose a binary/argv
- output behavior is deterministic and testable
- converted files do not silently retain arbitrary source metadata
- HEIC input works without a paid external API

Trade-offs:

- animated images are not yet supported
- metadata preservation is intentionally not a feature
- HEIF output is deferred
- exact compression ratios are not guaranteed by a preset name
