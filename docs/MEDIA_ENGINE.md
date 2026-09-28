# Media Engine

MEDIA-001 provides bounded common audio/video transformations through a trusted ffmpeg/ffprobe toolchain.

## Public operation model

The application exposes typed methods and fixed operation identities only:

- audio to MP3
- audio to M4A
- audio to WAV
- video to MP3
- mute video
- video to GIF
- video compression presets

There is no public argv, filter-string, executable-path, shell-command, codec-name, or muxer parameter.

## Probe

ffprobe runs with:

- a fixed executable path discovered from worker configuration
- shell disabled
- standard input disabled
- the protocol whitelist restricted to local file access
- a bounded JSON show_entries schema
- metadata tags excluded
- a hard timeout

Only container, duration, stream type/codec, audio shape and video dimensions are retained.

## Default policy

- input: 20 MiB
- output: 45 MiB
- duration: 10 minutes
- video: up to 3840 x 2160 and 8,294,400 pixels
- streams: 8
- GIF duration: 10 seconds
- GIF width: 640 pixels
- probe timeout: 10 seconds
- conversion timeout: 60 seconds
- captured process diagnostics: 1 MiB

## Containers/codecs

The MVP accepts a bounded allowlist of common local audio/video containers and codecs. Unsupported containers/codecs fail before conversion.

Output contracts are fixed:

- MP3: mp3 container + mp3 audio
- M4A: ISO BMFF/M4A container + AAC
- WAV: WAV + PCM s16le
- muted/compressed video: MP4 + MPEG-4 video; compressed output may contain AAC audio
- GIF: GIF video stream only

Every generated output is re-probed before it is eligible for delivery.

## Process safety

ffmpeg runs without a shell or interactive stdin. The child environment intentionally excludes application secrets such as Telegram and database credentials.

On timeout the process is killed and waited. Partial and final output paths created by a failed operation are removed.

This does not replace SEC-001 OS/container resource isolation. In particular, filesystem/network namespaces, cgroups and concurrency limits remain release blockers.
