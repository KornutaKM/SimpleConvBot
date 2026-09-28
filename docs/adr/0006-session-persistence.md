# ADR 0006 — PostgreSQL-authoritative multi-file sessions

Status: Accepted

## Context

Image-to-PDF and PDF merge need several Telegram messages to become one deterministic operation. Redis-only collection state would make restart recovery and ownership checks ambiguous.

## Decision

- PostgreSQL is authoritative for collection sessions and collected-file ordering.
- A session is bound to both owner user id and chat id.
- New files are serialized with a row-level session lock.
- Duplicate delivery is identified by `(session_id, source_message_id)`.
- Exact duplicate metadata is idempotent; conflicting duplicate metadata fails closed.
- File count and aggregate bytes are durable counters updated in the same transaction as file rows.
- Persisted positions are monotonically increasing and are never silently reordered after deletion.
- Finalization is an explicit COLLECTING -> FINALIZED transition and is idempotent.
- Finalization emits only a fixed operation identity plus ordered opaque input references.
- Expired COLLECTING sessions are deleted by a bounded reaper and child rows cascade.
- Original filenames are not stored in the session model.

## Consequences

Positive:

- restart-safe session state
- deterministic output ordering
- concurrent duplicate deliveries cannot exceed bounds through stale reads
- authorization is checked at every repository boundary
- the Telegram gateway and Railway deployment remain separate from collection state

Trade-offs:

- pre-alpha schema bootstrap still uses SQLAlchemy metadata creation; explicit migrations remain required before public schema evolution
- finalized-session retention and job linkage will be completed with the end-to-end Telegram/job wiring
