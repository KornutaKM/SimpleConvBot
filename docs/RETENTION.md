# Retention sweep

Private alpha needs one observable operation for cleaning ephemeral state.

RetentionSweepService composes the two existing authoritative cleanup paths:

- LocalTemporaryStorage.reap_expired for UUID job workspaces
- PostgresCollectionSessionRepository.reap_expired for abandoned collecting sessions

The sweep uses one explicit current timestamp so filesystem and PostgreSQL retention decisions are evaluated against the same time boundary.

## Metrics

Each sweep produces one cleanup metrics attempt.

Deleted count includes:

- stale workspaces successfully removed
- expired collection sessions removed from PostgreSQL

Failed count includes:

- workspace entries that could not be removed
- one additional failure if the workspace or session reaper raises

Exceptions are not swallowed. Metrics preserve the work already completed, then the failure propagates so an operator can see that the sweep was incomplete.

## Privacy

Retention evidence contains aggregate counts only. It does not expose workspace paths, filenames, session IDs, user IDs, chat IDs, Telegram message IDs, or object references.

## Scheduling

The Telegram runtime performs one retention sweep during startup and then runs a bounded periodic maintenance loop.

The effective private-alpha policy is configuration-driven:

- `TEMP_TTL_SECONDS` controls when a job workspace becomes eligible for deletion.
- `RETENTION_SWEEP_INTERVAL_SECONDS` controls how often the periodic sweep runs.
- the runtime emits one privacy-safe `retention_policy` event at startup with those two values.
- the evidence summarizer reports `max_cleanup_delay_seconds = ttl_seconds + sweep_interval_seconds` as the bounded worst-case scheduling delay for a continuously running process.

The initial startup sweep can remove already-expired state earlier than that worst-case periodic bound. Cleanup events remain aggregate-only and record deleted counts plus stable failure classes; they never expose workspace or session identity.
