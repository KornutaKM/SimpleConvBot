# Roadmap

The roadmap is gate-based. A phase is complete when its exit criteria are met, not when code merely exists.

## Phase 0 — Foundation

Deliverables:

- product contract
- MVP matrix
- architecture
- security/privacy contract
- implementation backlog
- contribution/development conventions

Exit:

- scope is explicit
- non-goals are explicit
- core state machine and security invariants are agreed

## Phase 1 — Control plane skeleton

Deliverables:

- Python project structure
- configuration model
- aiogram bot entrypoint
- FastAPI health endpoints if retained in deployment model
- PostgreSQL persistence
- Redis integration
- job model/state transitions
- operation registry
- idempotent Telegram update handling
- temporary storage abstraction
- test harness

Exit:

- a fake/no-op operation can travel through the full state machine
- duplicate update/callback tests pass
- restart behavior does not invent success

## Phase 2 — Image engine

Deliverables:

- robust image detection
- JPEG/PNG/WEBP conversion
- HEIC support
- compression presets
- resize
- image metadata
- output validation
- golden fixtures

Exit:

- advertised image workflows pass integration tests
- malformed/oversized image corpus fails safely

## Phase 3 — PDF engine

Deliverables:

- PDF validation/probe
- page count
- PDF to images
- image(s) to PDF
- merge
- split/extract
- bounded page selection through persisted fixed presets

Exit:

- malformed and pathological PDFs stay within limits
- merge ordering is deterministic
- output PDFs are validated

## Phase 4 — Media engine

Deliverables:

- ffprobe metadata
- audio conversion
- video audio extraction
- mute
- GIF conversion
- basic video compression
- named presets
- timeouts and resource classes

Exit:

- no user-provided arbitrary FFmpeg arguments
- media corpus includes unsupported codecs and corrupt containers
- output-size and timeout behavior is predictable

## Phase 5 — Multi-file sessions

Deliverables:

- collection/session model
- expiry
- add/remove-last/finalize flow with deterministic persisted ordering
- images to PDF
- PDF merge
- aggregate limits

Exit:

- abandoned sessions clean up
- ordering is explicit and reproducible
- one user cannot mutate another user's session

## Phase 6 — Security and resilience hardening

Deliverables:

- isolated worker runtime
- CPU/RAM/disk/process limits
- restricted network
- cleanup reaper
- rate limits
- structured error taxonomy
- adversarial corpus
- secrets/log review
- backup/restore for durable metadata only

Exit:

- all Security Release Gate items in SECURITY_PRIVACY.md pass

## Phase 7 — Private alpha

Deliverables:

- real Telegram bot deployment
- Russian and English UX
- health/metrics
- admin operational diagnostics
- representative real-file testing

During alpha, feature scope is frozen except for fixes required by evidence.

Exit:

- core workflows have acceptable completion rate
- no unexplained data-retention failures
- main failure classes are understood

## Phase 8 — Public MVP

Deliverables:

- BotFather profile and commands
- public privacy notice
- terms/acceptable-use basics as needed
- production deployment runbook
- alerting
- abuse controls
- release checklist

Exit:

- production readiness review passed

## Post-MVP gates

### Large file gate

Measure the distribution of rejected files and user demand.

Only if justified:

- deploy Telegram Local Bot API
- support larger inputs/outputs
- revisit storage and bandwidth architecture

### Mini App gate

Build a Mini App only when chat UI becomes a measured constraint, for example:

- visual PDF page selection
- crop UI
- complex batch management
- media timeline

### Monetization gate

Consider monetization only after repeat usage and resource cost are measured.

Possible future differentiators:

- larger limits
- priority queue
- batch processing
- longer-lived history where privacy expectations are explicit

The free core should remain useful.
