# SimpleConvBot Privacy Notice

Last updated: 2026-09-29

SimpleConvBot is a Telegram file-conversion bot. This notice describes the data
handled by the current public-MVP implementation. Telegram itself also processes
messages and files under Telegram's own terms and privacy policy.

## Files you send

SimpleConvBot downloads a supported file only when it is needed for the
conversion you selected.

File contents are stored in an isolated temporary workspace. On a normal
successful or failed operation the workspace is cleaned immediately after the
operation lifecycle completes. Abandoned workspaces have a one-hour TTL and are
checked by the cleanup service once per minute, so a stale workspace may remain
until the next sweep after its TTL expires.

The service does not intentionally keep uploaded file contents or generated
output files as long-term product storage.

## Multi-file operations

Images-to-PDF and PDF-merge flows temporarily store collection state so that the
bot can associate multiple Telegram files with one operation. Collection
sessions expire after one hour. Their temporary routing pointers expire with the
session.

## Operational metadata

The service stores limited operational records needed for idempotency,
recovery, abuse controls, and reliability. Depending on the path, these records
can include:

- Telegram update identifiers;
- pseudonymous Telegram user and chat identifiers;
- internal job/session identifiers;
- operation name/version and job state;
- source Telegram message identifier;
- timestamps.

These records do **not** contain the uploaded file contents or original
filenames.

Completed/terminal job records and Telegram update-receipt records become
eligible for automatic deletion after seven days. The same retention sweep that
cleans temporary state performs this metadata cleanup. Active jobs are not
deleted merely because they are old.

This seven-day operational-metadata window is separate from the one-hour file
workspace/session policy.

## Recovery backups

The production database may use bounded provider recovery snapshots. For the
first Railway public deployment, the approved policy is a daily PostgreSQL
volume backup schedule with snapshots retained for up to six days.

A record already removed from the live database can therefore remain inside an
older recovery snapshot until that snapshot expires. Recovery snapshots are used
only for disaster recovery, are not queried as product data, and do not contain
temporary conversion workspaces because the app workspace is not placed on the
database volume.

Longer weekly/monthly backup schedules or a longer point-in-time-recovery window
require a privacy/retention review before they are enabled.

## Short-lived Redis data

The current runtime uses Redis for short-lived control data:

- a locale hint keyed by Telegram user ID: up to 24 hours;
- active multi-file routing pointers: up to the collection-session lifetime
  (normally one hour);
- per-user rate-limit counters: about one minute;
- queue/control state needed while jobs are active.

Redis is not used as long-term file storage.

## Logs and diagnostics

Routine telemetry is designed to be aggregate and privacy-safe. It records
operation/stage outcomes, stable error classes, timings, health, cleanup counts,
and opaque internal correlation identifiers.

Routine telemetry must not include uploaded file contents, original filenames,
Telegram user/chat/message IDs, provider file references, bot tokens, database
URLs, Redis URLs, or authorization values. Runtime logging uses a final
redaction layer as defense in depth.

## Why data is processed

Data is processed only to:

- perform the conversion requested by the user;
- deliver the result;
- prevent duplicate processing and abuse;
- recover safely after process interruption;
- operate, secure, and diagnose the service.

SimpleConvBot does not use generative AI for file conversion.

## Security and limits

Files are treated as untrusted input. Operations are selected from a fixed
registry, resource limits are enforced, unsupported or malformed input fails
closed, and conversion work runs with bounded temporary storage and hardened
runtime controls.

With the standard Telegram Bot API used by the MVP, an input file that the bot
must download is limited to 20 MB. Files above that transport limit are rejected
before conversion with a user-facing size error.

## Changes

If storage, hosting, retention, or product behavior changes, this notice must be
updated before the changed behavior is presented as the public policy.

For implementation-level details, see `docs/SECURITY_PRIVACY.md`,
`docs/RETENTION.md`, and `docs/OBSERVABILITY.md`.
