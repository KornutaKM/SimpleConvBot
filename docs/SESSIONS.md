# Multi-file sessions

SESSION-001 adds durable collection state before a conversion job is created.

## Supported collection kinds

- `images_to_pdf` -> fixed operation `pdf.from_images`
- `pdf_merge` -> fixed operation `pdf.merge`

The collection layer does not execute conversion algorithms and does not contain Telegram/Railway deployment logic.

## Default policy

- maximum files: 20
- maximum aggregate input bytes: 40 MiB
- collection TTL: 1 hour

These are application policy defaults aligned with the current bounded PDF/image engine capacities. They remain explicit configuration in `SessionPolicy`.

## Identity and authorization

Every session is bound to:

- owner Telegram user id
- Telegram chat id
- session UUID

All read/mutation/finalization paths validate both owner and chat.

A collected file is idempotent by `(session_id, source_message_id)`. Re-delivery of the exact same file metadata is a no-op. Reuse of the same source message identity with different object reference or byte size fails closed as an idempotency conflict.

Original user filenames are not part of the session model.

## Ordering

Each accepted file receives a monotonically increasing persisted position while the session row is held `FOR UPDATE`.

Removing a file leaves a position gap rather than renumbering existing rows. This prevents reorder side effects. Snapshots and finalization plans always sort by persisted position, so the displayed order and execution order can use the same tuple.

## Limits and races

Add/remove/finalize operations lock the owning session row before reading or changing counters.

The transaction enforces:

- current state is COLLECTING
- session is not expired
- maximum file count
- maximum aggregate bytes
- unique source message identity
- unique monotonic position

This prevents concurrent Telegram deliveries from independently passing stale limits.

## Finalization

Finalization is explicit and idempotent.

The first finalization changes state from COLLECTING to FINALIZED and returns an immutable `FinalizedSessionPlan` containing the fixed operation id and ordered input references. Repeated finalization returns the same plan.

Expired collecting sessions cannot finalize.

## Cleanup

The reaper deletes expired COLLECTING sessions. Child file rows use PostgreSQL `ON DELETE CASCADE`.

Finalized sessions are not deleted by the abandoned-session reaper because they may already be referenced by subsequent job creation/delivery bookkeeping.
