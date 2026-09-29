# Private Telegram deployment

This runbook is the operational procedure for the SimpleConvBot private alpha.
It is not the public-release procedure.

## Runtime shape

Deploy exactly three services in one Railway project:

1. SimpleConvBot application service from the GitHub repository.
2. PostgreSQL.
3. Redis.

The bot uses Telegram long polling, so the application service does not need a
public HTTP domain.

Run exactly **one** application replica while polling is used. Multiple
replicas with the same bot token would compete for Telegram updates.

## Application service

Source:

- GitHub repository: `KornutaKM/SimpleConvBot`
- branch: `main`
- production entrypoint: `python -m simpleconvbot`

The repository root contains the production `Dockerfile`. Railway should
build it automatically. Do not override the command unless there is a specific
operational reason.

Before an alpha run, record the exact `main` commit deployed. For
GitHub-triggered deployments Railway also provides `RAILWAY_GIT_COMMIT_SHA`
and `RAILWAY_DEPLOYMENT_ID`; these are deployment identifiers, not secrets.

## Required variables

Set these variables on the application service:

```text
APP_ENV=production
LOG_LEVEL=INFO
TELEGRAM_BOT_TOKEN=<BotFather secret>
DATABASE_URL=${{Postgres.DATABASE_URL}}
REDIS_URL=${{Redis.REDIS_URL}}
TEMP_ROOT=/app/var/jobs
TEMP_TTL_SECONDS=3600
RETENTION_SWEEP_INTERVAL_SECONDS=60
DIAGNOSTICS_INTERVAL_SECONDS=300
```

If the database service names are not `Postgres` and `Redis`, use the
actual Railway service names in the reference expressions.

`RETENTION_SWEEP_INTERVAL_SECONDS` must be positive and must not exceed
`TEMP_TTL_SECONDS`. The runtime performs an initial fail-closed retention
sweep before polling, then repeats bounded sweeps periodically.

`DIAGNOSTICS_INTERVAL_SECONDS` controls aggregate operational diagnostics.
Startup also performs a bounded PostgreSQL/Redis health probe and does not
start Telegram polling if dependencies are not ready.

`TELEGRAM_BOT_TOKEN` is a secret. Never commit it to this repository, an
issue, a pull request, logs, or chat.

The application accepts provider PostgreSQL URLs beginning with
`postgres://` or `postgresql://` and normalizes them to the SQLAlchemy
asyncpg driver internally.

## PostgreSQL

Add Railway PostgreSQL to the same project.

The application currently bootstraps its pre-alpha schema at startup with
SQLAlchemy metadata creation. Explicit database migrations are still required
before schema evolution or public release.

Do not expose PostgreSQL publicly for this bot deployment.

## Redis

Add Railway Redis to the same project.

Redis is used for the job queue, rate-limit counters, collection routing focus,
and short-lived RU/EN locale hints. PostgreSQL remains authoritative for jobs
and collection-session state.

Do not expose Redis publicly for this deployment.

## Operational diagnostics

The runtime emits structured `admin_diagnostic` JSON at startup and then at
the configured diagnostics interval. The payload is aggregate-only and
contains:

- package version and environment;
- process uptime;
- PostgreSQL and Redis health state, latency, and exception type only;
- per-operation stage totals, successes, failures, and duration aggregates;
- stable failure-class counts by operation, stage, and error_code;
- retention cleanup aggregate counters.

Operation stages cover validation, queue, worker, upload, and cleanup paths.
The diagnostic payload must not contain Telegram user/chat IDs, original
filenames, Telegram provider file references, message contents, tokens,
database URLs, or Redis URLs.

A failed periodic health probe is observable in the next diagnostic payload but
does not by itself terminate an already-running bot. Startup dependency health
is fail-closed.

All runtime log records pass through a final redacting formatter after exception
traceback formatting. This is intended to prevent third-party exception strings
from exposing the bot token, PostgreSQL/Redis URLs, Authorization values,
provider file paths, or filename/file-path fields. The redactor is defense in
depth; routine logs must still be reviewed during alpha.

## Deployment settings

Private-alpha settings:

- replicas: 1
- restart policy: On Failure
- public networking: disabled
- GitHub auto-deploy: `main` only after CI succeeds

Do not treat the private application service itself as proof of kernel-level
worker egress isolation. The CI hardened-container profile remains the
repository proof for the worker sandbox boundary.

## First launch verification

After deployment:

1. Confirm the Railway deployment is built from the intended exact `main`
   commit.
2. Confirm startup succeeds through PostgreSQL schema initialization, Redis
   connectivity, startup job reconciliation, the initial retention sweep, and
   the initial `admin_diagnostic` with `health.ready=true`.
3. Confirm Telegram long polling remains running with exactly one replica.
4. Open `@KoxConv_bot` and send `/start`.
5. Verify navigation in both Russian and English Telegram locales.
6. Run at least one real file through each enabled family:
   - image conversion/compression;
   - PDF to images;
   - audio conversion;
   - video operation;
   - images to PDF collection;
   - PDF merge collection.
7. Exercise bounded failure paths:
   - unsupported input;
   - oversized input (must report a size-limit error, not a generic download failure);
   - duplicate callback/update;
   - restart during or around queued work.
8. Verify the `admin_diagnostic` operation-stage aggregates move for the
   exercised operations, failure-class counts use only stable error codes, and
   cleanup counters are attributable.
9. Verify result delivery and cleanup evidence without recording filenames,
   provider file references, user/chat IDs, message contents, tokens, database
   URLs, or Redis URLs.
10. Leave the deployment running beyond one retention interval and verify that
    no unexplained stale workspace/session remains.

Use `docs/PRIVATE_ALPHA.md` as the acceptance record. Do not check an item
from repository CI alone when the checklist explicitly requires real Telegram
evidence.

## Rollback

If a new deployment fails, roll back the application service to the previous
known-good GitHub deployment. Record both the failed and rollback commit
identities.

Do not change database contents manually as part of a routine application
rollback.

If polling behaves unexpectedly, stop extra application replicas first and
verify that only one instance is using the bot token.

### Restart semantics

At startup the runtime reconciles durable PostgreSQL state with Redis:

- Redis reserved/inflight queue entries are returned to the ready queue;
- durable `QUEUED` jobs are enqueue-safe again, even if the prior process died
  between the PostgreSQL state transition and Redis enqueue;
- `RECEIVED`, `VALIDATING`, `PROCESSING`, and `UPLOADING` jobs are treated
  as interrupted, their workspaces are cleaned, and they transition to
  `FAILED`;
- an interrupted `UPLOADING` job is **not uploaded again**, because the prior
  Telegram request may already have succeeded before the process died;
- an unexpected queue-worker task failure terminates the application runtime instead of
  leaving Telegram polling alive without a worker; the hosting restart then enters this
  same reconciliation path;
- the user receives a bounded RU/EN restart message telling them to resend only
  if no result arrived.

A cleanup failure aborts startup before that interrupted job is marked failed,
so a subsequent restart can retry cleanup rather than silently orphaning data.

## Secret rotation

If the Telegram token is ever exposed:

1. Revoke/regenerate it in BotFather.
2. Replace `TELEGRAM_BOT_TOKEN` in the hosting provider.
3. Redeploy/restart the application service.
4. Do not preserve the old token in repository history or incident notes.
