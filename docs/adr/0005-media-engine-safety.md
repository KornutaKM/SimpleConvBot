# ADR 0005 — Fixed-argv FFmpeg media worker

Status: Accepted

## Context

FFmpeg is powerful enough to become an arbitrary execution surface if user input can select executable paths, arguments, protocols, filters, codecs or output destinations.

The media MVP only needs a small set of common transformations.

## Decision

- Treat ffmpeg and ffprobe executable paths as trusted worker configuration.
- Never expose raw FFmpeg argv or filter strings to product inputs.
- Build commands from typed operation enums and fixed presets.
- Run subprocesses with shell disabled, stdin disabled, a minimal environment, bounded diagnostics and hard timeouts.
- Restrict input protocols to local file access.
- Probe before conversion and reject inputs outside explicit byte, duration, stream, codec and resolution bounds.
- Strip input metadata/chapters on generated media.
- Write to a job-local partial path and publish only after byte checks and independent ffprobe validation.
- Use native FFmpeg MPEG-4/AAC/PCM/GIF paths plus libmp3lame for the MVP outputs.
- Install ffmpeg/ffprobe in production/development images and verify their presence in CI.

## Consequences

Positive:
- users cannot inject arbitrary FFmpeg arguments
- outputs have stable codec/container contracts
- timeouts terminate the media subprocess
- routine child processes do not inherit application secrets

Trade-offs:
- the OS package version is part of the current pre-alpha runtime image rather than a separately vendored static binary
- the initial codec/container allowlist is intentionally narrow
- stronger filesystem/network/process isolation remains SEC-001 work
