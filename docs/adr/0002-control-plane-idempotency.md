# ADR 0002 — PostgreSQL state authority and at-least-once Redis queue

Status: Accepted

## Context

Telegram may redeliver updates, users may press an operation button more than once, workers may restart, and a queue may contain duplicate deliveries.

Treating queue uniqueness as the correctness boundary would make conversion execution depend on fragile timing.

## Decision

- PostgreSQL is authoritative for durable job identity and state.
- Telegram update IDs are claimed durably before handler execution.
- A logical conversion has a unique idempotency key derived from Telegram chat/user/source-message plus operation identity/version.
- Redis is an at-least-once work transport.
- Duplicate Redis entries are permitted.
- A worker may execute only after winning the atomic durable transition `QUEUED -> PROCESSING`.
- A second delivery of the same logical job observes a non-QUEUED state and performs no execution.
- Jobs use an explicit monotonic state machine.
- Process/repository startup does not reinterpret uncertain states as success.

The initial Redis adapter uses ready and processing lists. Reserved items remain in the processing list until acknowledged, and can be moved back to ready by explicit recovery.

## Consequences

Positive:

- double clicks do not create a second logical job
- duplicate Telegram delivery does not duplicate handler side effects
- duplicate queue delivery does not duplicate operation execution
- PostgreSQL state can be audited independently of Redis

Trade-offs:

- Redis may contain redundant work items
- recovery policy for abandoned processing entries must remain explicit
- later production worker orchestration must define lease/recovery timing rather than silently guessing that a job succeeded
