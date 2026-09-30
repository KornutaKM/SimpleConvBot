# Railway production runbook

Railway is the selected hosting path for the first public SimpleConvBot MVP.
This document is provider-specific evidence guidance; it does not by itself prove
that a Railway project is configured or healthy.

Official references:

- https://docs.railway.com/builds/dockerfiles
- https://docs.railway.com/databases/postgresql
- https://docs.railway.com/databases/redis
- https://docs.railway.com/variables
- https://docs.railway.com/deployments/deployment-teardown
- https://docs.railway.com/deployments/restart-policy
- https://docs.railway.com/volumes/backups

## Project shape

Create one Railway project/environment with exactly three services:

1. `SimpleConvBot` — this GitHub repository, deployed from the exact reviewed
   `main` revision.
2. `Postgres` — Railway PostgreSQL.
3. `Redis` — Railway Redis.

Keep PostgreSQL and Redis private. SimpleConvBot uses Telegram long polling and
does not require a public HTTP domain for the MVP.

The app service must have exactly one replica. Horizontal or multi-region app
replicas are not allowed while one Telegram bot token is shared.

## Build and start

Railway detects the repository-root `Dockerfile` automatically. Do not add a
legacy `railway.toml` / `railway.json` for this new service; Railway's older
Config as Code path is deprecated for new services.

Do not override the image start command unless a reviewed release explicitly
changes it. The Dockerfile starts:

```text
python -m simpleconvbot
```

## App variables

Set these on the `SimpleConvBot` service:

```text
APP_ENV=production
TELEGRAM_BOT_TOKEN=<provider secret>

DATABASE_URL=${{Postgres.DATABASE_URL}}
REDIS_URL=${{Redis.REDIS_URL}}

TEMP_ROOT=/app/var/jobs
TEMP_TTL_SECONDS=3600
METADATA_TTL_SECONDS=604800
RETENTION_SWEEP_INTERVAL_SECONDS=60
DIAGNOSTICS_INTERVAL_SECONDS=300

RUNTIME_LEASE_TTL_SECONDS=30
RUNTIME_LEASE_ACQUIRE_TIMEOUT_SECONDS=45

WORKSPACE_MAX_BYTES=67108864
UPDATE_RATE_LIMIT_PER_MINUTE=60
MAX_ACTIVE_JOBS_PER_USER=3
MAX_ACTIVE_JOBS_GLOBAL=32

RAILWAY_DEPLOYMENT_OVERLAP_SECONDS=0
RAILWAY_DEPLOYMENT_DRAINING_SECONDS=20
```

If the database services use different Railway service names, update the
reference-variable namespaces instead of copying literal connection strings.

Do not enable public access on PostgreSQL or Redis for normal bot operation.

## Singleton runtime handoff

SimpleConvBot uses a Redis-backed runtime lease around startup recovery,
retention, diagnostics, queue worker, and Telegram polling.

Expected deployment behavior:

1. the old deployment owns the lease;
2. the new deployment starts and waits without running owned application work;
3. Railway begins teardown of the old deployment;
4. the old deployment releases the lease on graceful shutdown, or the lease
   expires after the bounded TTL if it is hard-killed;
5. the new deployment acquires the lease and starts recovery/polling/worker.

If ownership is lost after startup, the lease guard fails closed and cancels the
owned runtime. A second instance must never continue polling or working jobs
without current lease ownership.

Keep Railway deployment overlap at zero. The runtime lease is defense in depth,
not permission to configure multiple application replicas.

## Restart policy

Set the app service restart policy to **On Failure**. A bounded retry policy is
preferred over an unlimited restart loop because persistent dependency,
configuration, or lease failures require operator attention.

A crash/restart is not release evidence by itself. After any restart, verify the
startup sequence and the current deployment identity.

## Storage

Do not attach a persistent volume to the app service. Conversion workspaces are
temporary and must remain outside durable backups.

PostgreSQL is the durable metadata store. Redis is control/queue state and must
remain a private service in the same Railway environment.

## PostgreSQL backup policy

For the first public MVP:

- enable Railway **daily** Postgres volume backups;
- keep Railway's daily retention (currently six days);
- do not enable weekly or monthly volume backup schedules for RELEASE-001;
- do not enable a longer PITR window unless the public privacy notice and
  RELEASE-001 retention decision are reviewed first.

Backups are recovery-only. Operational metadata removed from the live database
after its seven-day TTL can remain inside an older recovery snapshot until that
snapshot expires. The public privacy notice discloses this separately.

Record the configured backup schedule and retention as production evidence.

## First deployment evidence

Capture without exposing secrets:

- exact Git commit SHA;
- Railway deployment ID and service name;
- immutable image identity when available;
- region;
- app replica count = 1;
- restart policy;
- teardown overlap/drain values;
- PostgreSQL and Redis service identities;
- backup schedule/retention;
- startup log evidence for schema, recovery, initial retention, dependency
  health, runtime lease acquisition, Telegram polling, and worker activity.

Do not paste rendered `DATABASE_URL`, `REDIS_URL`, or bot tokens into GitHub
issues or chat.

After the deployment identity is known, initialize the local
`.production-review.json` with `scripts/production_review.py`. Use that
commit/deployment-bound manifest for every remaining RELEASE-001 external and
final-approval gate. The manifest is intentionally ignored by Git.

## Production smoke

Run the matrix in `docs/PRODUCTION.md` against the production bot. In addition,
verify:

- only one deployment currently owns the runtime lease;
- no `TelegramConflictError` occurs during initial deployment;
- one controlled redeploy transfers lease ownership without concurrent polling;
- the new deployment resumes Telegram processing after the old deployment
  leaves;
- cleanup and diagnostics continue after the handoff.

## Rollback

Use Railway's rollback action to restore the previous known-good deployment
image and its deployment variables. The singleton lease still applies during the
handoff.

After rollback, verify the exact rollback deployment identity, lease acquisition,
dependency health, Telegram polling, and at least one conversion.

Do not restore the temporary app workspace. Restore PostgreSQL only for a
database incident, not as part of routine application rollback.
