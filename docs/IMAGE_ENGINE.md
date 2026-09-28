# Image Engine

IMG-001 introduces the first deterministic conversion engine.

## Supported input

Content-detected single-frame:

- JPEG
- PNG
- WEBP
- HEIF/HEIC

The filename extension and Telegram-provided MIME type are not trusted for image identity.

## Supported output

- JPEG
- PNG
- WEBP

HEIF/HEIC is an input format in v0.1, not an advertised output format.

## Safety policy

Default bounds:

- input file bytes: 20 MiB
- width: 16,384 px
- height: 16,384 px
- total pixels: 40,000,000
- output file bytes: 45 MiB

These are application safety limits, not claims about the maximum capability of Pillow/libheif.

Input bytes are checked before the decoder is opened. Pillow decompression-bomb warnings and errors are promoted to hard failures. Application dimension/pixel checks are applied before full image decoding whenever the decoder exposes dimensions at open time.

HEIF thumbnails are disabled and HEIF decoding is configured for one decode thread in this worker implementation.

Multi-frame/animated images are rejected in the first image MVP instead of silently dropping frames.

## Metadata

Transforms intentionally do not preserve arbitrary source EXIF/XMP metadata. This reduces accidental location/device metadata leakage in converted outputs.

EXIF orientation is applied to pixels before output.

## Transparency

PNG/WEBP output preserves alpha when present.

JPEG has no alpha channel. Transparent input converted to JPEG is composited onto a white background.

## Resize semantics

- percent scales both dimensions
- width-only preserves aspect ratio
- height-only preserves aspect ratio
- width+height means fit within that box while preserving aspect ratio

Resolved output dimensions must remain within image policy bounds.

## Compression presets

The public model is:

- best
- balanced
- smallest

Numeric encoder settings are internal policy and may evolve without changing the user-facing contract.

## Failure classes

Stable image-engine codes:

- input_too_large
- unsupported_type
- corrupt_input
- dimensions_exceeded
- pixels_exceeded
- multi_frame_unsupported
- invalid_parameters
- output_too_large
- output_validation_failed

Telegram wording/localization should map from these codes rather than parsing exception text.

## Test corpus

The committed Base64 corpus includes malformed input and a PNG header declaring 50,000 x 50,000 pixels without allocating that decoded image. Codec round-trip coverage exercises JPEG, PNG, WEBP and HEIF using the exact-pinned runtime codecs.
