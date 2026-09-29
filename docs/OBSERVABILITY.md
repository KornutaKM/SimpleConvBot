# Observability contract

SimpleConvBot records production evidence without turning logs or metrics into a
second store of user data. ALPHA-001 validated the runtime telemetry paths; the
same privacy-safe contract is used for RELEASE-001 production monitoring.

## Structured events

Telemetry events are JSON objects with a closed field set:

- event
- timestamp
- operation_id
- stage
- outcome
- duration_ms
- stable error_code
- opaque correlation_id
- aggregate count

The event API has no filename, path, Telegram user/chat/message identifier, file_id, URL, exception message, token, database URL, or Redis URL field.

Correlation IDs are short deterministic hashes of random internal job UUIDs. They support log correlation without exposing the durable UUID itself.

## Operation stages

The canonical stages are:

- validation
- queue
- worker
- upload
- cleanup

This lets alpha failures be attributed to a stage without parsing free-form text.

## Metrics

The in-process registry aggregates by operation identity and stage:

- total executions
- successes
- failures
- duration count/sum/max
- cleanup attempts/deleted/failed

Metrics deliberately do not have per-user, per-chat, per-filename, or per-message labels. High-cardinality user data must not become telemetry dimensions.

## Health

The health collector checks PostgreSQL and Redis with bounded timeouts.

A component health record contains only:

- component name
- up/down state
- latency
- exception type on failure

Exception messages and connection URLs are not emitted because they can contain provider details or credentials.

## Admin diagnostics

The non-UI AdminDiagnostics model combines:

- application version
- environment name
- uptime
- aggregate health
- aggregate metrics

It intentionally has no endpoint/credential/user/file fields. A later private-alpha admin command or health surface may serialize this model directly instead of inventing a new diagnostics schema.

## Integration point for the Telegram bot

The parallel Telegram implementation should consume these primitives rather than logging raw Message/Document objects.

Recommended mapping:

1. validation starts when Telegram file metadata has passed transport-level checks
2. queue covers durable job creation/enqueue
3. worker covers download plus engine execution only when the isolated worker boundary is actually used
4. upload covers Telegram result delivery
5. cleanup covers workspace/result deletion

Only stable engine/control-plane error codes should enter telemetry. Raw exception text, source filenames, Telegram file paths and provider URLs stay out of routine logs.

## Production alerting

The selected hosting/monitoring provider must make runtime liveness, dependency
health, restart loops, cleanup failures, and stable operation failure classes
actionable without adding user/file identity to alert labels.

The provider-neutral alert conditions and release smoke procedure are defined
in `docs/PRODUCTION.md`.

## Validation status

ALPHA-001 completed real Telegram evidence for validation, queue, worker,
upload, cleanup, recovery, duplicate-update suppression, retention, and RU/EN
manual UX. RELEASE-001 must still observe the exact deployed production
revision rather than treating historical alpha evidence as production health.
