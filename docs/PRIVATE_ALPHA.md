# Private alpha checklist

This checklist is the evidence gate for ALPHA-001. It distinguishes repository-proven behavior from work that still requires the real Telegram deployment.

## Already proven in repository CI

- [x] deterministic Image engine with hostile-input bounds
- [x] deterministic PDF engine with dual-parser validation and bounded rendering
- [x] fixed-argv Media engine with timeout and output validation
- [x] durable PostgreSQL job state and Redis queue semantics
- [x] multi-file collection sessions with owner/chat binding
- [x] per-user/global admission and request-rate primitives
- [x] hardened worker profile proof in CI
- [x] dependency vulnerability audit
- [x] privacy-safe structured telemetry schema
- [x] PostgreSQL/Redis health probes
- [x] aggregate operation/cleanup metrics primitives
- [x] live operation stage telemetry feeds one shared aggregate metrics registry
- [x] startup + periodic PostgreSQL/Redis health diagnostics are wired into runtime
- [x] aggregate admin diagnostics are emitted without user/chat/file identity
- [x] runtime log formatter redacts secrets/provider URLs/file fields after traceback formatting
- [x] bounded retention sweep for stale workspaces and expired collection sessions
- [x] production runtime startup + periodic retention sweep wiring
- [x] real Telegram execution wiring for image/PDF/media operations
- [x] real Telegram multi-file wiring for images-to-PDF and PDF merge
- [x] RU/EN routing through gateway, sessions and queued delivery

## Telegram end-to-end evidence still required

Do not mark these complete from engine/unit tests alone.

- [ ] real Telegram image upload -> validation -> conversion -> result upload -> cleanup
- [ ] real Telegram PDF upload -> operation -> result upload -> cleanup
- [ ] real Telegram media upload -> operation -> result upload -> cleanup
- [ ] multi-message images-to-PDF collection -> final result
- [ ] multi-message PDF merge collection -> final result
- [ ] duplicate callback/update does not cause duplicate conversion
- [ ] oversized/unsupported Telegram files receive useful bounded errors
- [ ] process/app restart does not invent success or lose attributable failure state
- [ ] routine logs contain no original filename, Telegram file path, user/chat identity, token, DB URL, or Redis URL
- [ ] cleanup occurs after success and failure within the documented retention window
- [ ] Russian UX covers all enabled operations and failures
- [ ] English UX covers all enabled operations and failures

## Representative alpha corpus

The private alpha should keep a local/non-repository corpus unless redistribution rights are explicit. For each supported family, record only the fixture class and expected result in test evidence; do not upload user files to GitHub.

Minimum image cases:

- normal phone JPEG
- transparent PNG
- WEBP
- HEIC/HEIF
- EXIF orientation
- corrupt/truncated input
- extension/MIME spoof
- pixel/dimension limit rejection
- output-size rejection

Minimum PDF cases:

- one-page PDF
- multi-page PDF
- image-to-PDF
- ordered merge
- page extraction
- encrypted PDF rejection
- corrupt/truncated PDF
- oversized page/render rejection
- output-size rejection

Minimum media cases:

- WAV -> MP3
- audio -> M4A
- audio -> WAV
- video -> MP3
- mute video
- short GIF conversion
- video compression
- corrupt container
- unsupported codec/container
- duration/resolution/output-size rejection
- timeout path

## Evidence record per run

Start every run by recording the exact GitHub `main` commit and the Railway
deployment identity. Do not mix evidence from different deployed revisions.

Record aggregate operational evidence only:

- build/main commit SHA
- deployment identity/version
- operation_id
- stage
- success/failure
- stable error_code when failed
- duration
- cleanup outcome
- expected vs actual user-visible result

Do not record original filenames, Telegram file paths, user/chat IDs, provider URLs, secrets, or message contents.

## Release boundary

ALPHA-001 is not complete until the real Telegram bot code is present in GitHub and the deployed private-alpha path demonstrates the unchecked end-to-end items above. The current engine/control-plane/observability evidence is necessary but not a substitute for that deployment evidence.
