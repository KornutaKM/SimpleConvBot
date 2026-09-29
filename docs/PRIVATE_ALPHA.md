# Private alpha checklist

This checklist is the evidence gate for ALPHA-001. It distinguishes repository-proven behavior from work that still requires the real Telegram runtime.

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
- [x] stable operation failure classes are aggregated by operation/stage/error_code
- [x] runtime log formatter redacts secrets/provider URLs/file fields after traceback formatting
- [x] bounded retention sweep for stale workspaces and expired collection sessions
- [x] production runtime startup + periodic retention sweep wiring
- [x] startup recovery requeues QUEUED jobs and fails interrupted active jobs closed without re-upload
- [x] unexpected queue-worker task failure tears down polling so restart recovery can run
- [x] real Telegram execution wiring for image/PDF/media operations
- [x] real Telegram multi-file wiring for images-to-PDF and PDF merge
- [x] RU/EN routing through gateway, sessions and queued delivery
- [x] known oversized Telegram inputs fail before provider download with a stable RU/EN size-limit error
- [x] local Docker Compose alpha profile runs app + PostgreSQL + Redis with health-gated dependencies and bounded app runtime settings

## Enabled private-alpha surface

The Telegram menus expose only operations that are wired end to end. Future and incomplete tools stay hidden until their implementation is ready for alpha evidence. This prevents prototype callbacks from being presented as usable features.

## Telegram end-to-end evidence still required

Do not mark these complete from engine/unit tests alone.

- [x] real Telegram image upload -> validation -> conversion -> result upload -> cleanup
- [x] real Telegram PDF upload -> operation -> result upload -> cleanup
- [x] real Telegram media upload -> operation -> result upload -> cleanup
- [ ] multi-message images-to-PDF collection -> final result
- [ ] multi-message PDF merge collection -> final result
- [ ] duplicate callback/update does not cause duplicate conversion
- [ ] oversized/unsupported Telegram files receive useful bounded errors
- [ ] process/app restart does not invent success or lose attributable failure state
- [x] routine logs contain no original filename, Telegram file path, user/chat identity, token, DB URL, or Redis URL
- [ ] cleanup occurs after success and failure within the documented retention window
- [ ] Russian UX covers all enabled operations and failures
- [ ] English UX covers all enabled operations and failures


### Bound RU/EN manual review

Machine telemetry cannot prove that every enabled user-visible path is understandable in both
languages. Record that part separately in a local JSON file bound to the exact git revision and
runtime identity.

Initialize a review after the local runtime has been rebuilt:

```powershell
$imageId = docker inspect simpleconvbot-app-1 --format '{{.Image}}'
python scripts/alpha_review.py init --output .alpha-review.json --execution-mode compose --runtime-id $imageId
```

The review contains these fixed checks for each locale:

- `home_and_tools_navigation`
- `image_actions`
- `pdf_actions`
- `audio_actions`
- `video_actions`
- `images_to_pdf_collection`
- `pdf_merge_collection`
- `unsupported_input_error`
- `oversized_input_error`
- `generic_failure_error`
- `settings_and_back_navigation`

Mark only what was actually observed. Example:

```powershell
python scripts/alpha_review.py mark --input .alpha-review.json --locale ru --check image_actions --status pass
```

After a complete locale review, `--check all --status pass` is allowed as an explicit human
attestation that every fixed check above was exercised for that locale. The CLI refuses to mutate
a review whose commit no longer matches the current `git HEAD`.

Combine manual and machine evidence:

```powershell
docker compose logs --since=30m app > alpha-runtime.log
python scripts/alpha_evidence.py --input alpha-runtime.log --manual-review .alpha-review.json --require-all-gates
$LASTEXITCODE
```

Exit code `0` means both machine-verifiable gates and the commit-bound RU/EN manual review are
complete. Exit code `2` means at least one gate remains pending. Keep `.alpha-review.json` and
raw runtime logs local; do not commit them.

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

Start every run by recording the exact GitHub `main` commit and the local execution identity. Do not mix evidence from different revisions or rebuilt images.

For Compose runs record the app image ID. For host-Python runs record the exact checked-out Git commit. A remote deployment identity is not required for the current alpha.

Record aggregate operational evidence only:

- build/main commit SHA
- execution mode (`compose` or `host-python`)
- local app image ID when applicable
- operation_id
- stage
- success/failure
- stable error_code when failed
- aggregate failure-class count by operation/stage/error_code
- duration
- cleanup outcome
- expected vs actual user-visible result
- collection validation `count` as privacy-safe multi-file cardinality evidence
- `update_deduplicated` events as duplicate-update suppression evidence
- `input_rejected` events as aggregate unsupported/oversized rejection evidence
- `recovery_summary` events as aggregate startup-recovery evidence
- `retention_policy` events as the effective TTL/sweep-interval evidence

Do not record original filenames, Telegram file paths, user/chat IDs, provider URLs, secrets, or message contents.

After a local Compose run, generate the bounded evidence summary directly from logs:

```powershell
docker compose logs --since=10m app | python scripts/alpha_evidence.py
```

For a machine-verifiable gate check, use:

```powershell
docker compose logs --since=10m app | python scripts/alpha_evidence.py --require-runtime-gates
$LASTEXITCODE
```

Exit code `0` means every machine-verifiable runtime gate in the summary is PASS.
Exit code `2` means at least one such gate is still PENDING. This does not replace the
separate RU/EN user-visible review, which remains listed under
`runtime_gates.manual_review_remaining`.

The summarizer emits only allowlisted aggregate fields. It counts complete correlated E2E
operation runs, multi-file E2E runs, duplicate-update suppression, bounded input rejections,
startup recovery summaries with interrupted/requeued classification, effective retention
policy, retention cleanup, current health readiness, gate PASS/PENDING status, and the
latest aggregate failure classes. It never
echoes raw log lines or unknown payload fields.

Before public launch, use the aggregate failure-class counters from
`admin_diagnostic` to identify the dominant stable error codes observed during
the private alpha. Do not infer failure classes from user content or filenames.

## Release boundary

ALPHA-001 is not complete until the real Telegram bot code is present in GitHub and the local private-alpha runtime demonstrates the unchecked end-to-end items above. The current engine/control-plane/observability evidence is necessary but not a substitute for real Telegram runtime evidence.

Remote hosting is optional future infrastructure and is not an ALPHA-001 acceptance dependency unless the project explicitly adopts it later.
