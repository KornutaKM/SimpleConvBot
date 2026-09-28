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

This module does not start a scheduler or mutate the Railway runtime. The Telegram/deployment implementation may call the sweep from a bounded maintenance loop once that runtime code is merged and reviewed.
