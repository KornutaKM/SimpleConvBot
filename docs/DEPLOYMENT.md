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
```

If the database service names are not `Postgres` and `Redis`, use the
actual Railway service names in the reference expressions.

`RETENTION_SWEEP_INTERVAL_SECONDS` must be positive and must not exceed
`TEMP_TTL_SECONDS`. The runtime performs an initial fail-closed retention
sweep before polling, then repeats bounded sweeps periodically.

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
   connectivity, queue recovery, and the initial retention sweep.
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
   - oversized input;
   - duplicate callback/update;
   - restart during or around queued work.
8. Verify result delivery and cleanup evidence without recording filenames,
   provider file references, user/chat IDs, message contents, tokens, database
   URLs, or Redis URLs.
9. Leave the deployment running beyond one retention interval and verify that
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

## Secret rotation

If the Telegram token is ever exposed:

1. Revoke/regenerate it in BotFather.
2. Replace `TELEGRAM_BOT_TOKEN` in the hosting provider.
3. Redeploy/restart the application service.
4. Do not preserve the old token in repository history or incident notes.
