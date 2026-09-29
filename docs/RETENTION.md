# Retention sweep

SimpleConvBot uses one observable maintenance sweep for ephemeral file state,
multi-file session state, and bounded operational metadata.

`RetentionSweepService` composes three authoritative cleanup paths:

- `LocalTemporaryStorage.reap_expired` for UUID job workspaces;
- `PostgresCollectionSessionRepository.reap_expired` for expired collection
  sessions;
- `PostgresOperationalMetadataReaper.reap_expired` for terminal job rows and
  Telegram update receipts older than the metadata TTL.

One explicit current timestamp is used for all retention decisions in a sweep.

## Current policy

The public-MVP defaults are:

- temporary job workspace TTL: 3600 seconds (1 hour);
- collection session TTL: 3600 seconds (1 hour);
- terminal job/update-receipt metadata TTL: 604800 seconds (7 days);
- periodic retention sweep interval: 60 seconds.

Normal operation cleanup removes job workspaces immediately after success or
failure. The workspace TTL is a recovery boundary for abandoned state, not a
promise that every file waits one hour before deletion.

Active jobs are never deleted by the age-based metadata reaper. Only terminal
job states are eligible.

## Metrics

Each sweep produces one aggregate cleanup metrics attempt.

Deleted count includes:

- stale workspaces successfully removed;
- expired collection sessions;
- expired terminal job records;
- expired Telegram update receipts.

Failed count includes workspace-level failures plus a bounded failure increment
if a reaper raises. Exceptions are not swallowed: the failure propagates so the
operator can see that the sweep was incomplete.

## Privacy

Retention evidence contains aggregate counts only. It does not expose workspace
paths, filenames, session IDs, Telegram user/chat/message IDs, provider file
references, or file contents.

The public policy is documented in `docs/PRIVACY.md`.

## Scheduling

The Telegram runtime performs one retention sweep during startup and then runs a
bounded periodic maintenance loop.

Configuration:

- `TEMP_TTL_SECONDS` controls abandoned workspace eligibility;
- `METADATA_TTL_SECONDS` controls terminal job/update-receipt eligibility;
- `RETENTION_SWEEP_INTERVAL_SECONDS` controls periodic sweep frequency.

The runtime emits the temporary-workspace retention policy as privacy-safe
aggregate telemetry. Cleanup events remain aggregate-only and record deletion
counts plus stable failure classes.
