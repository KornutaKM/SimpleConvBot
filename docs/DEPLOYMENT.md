# Private Telegram alpha — local runtime

This runbook is the current operational procedure for the SimpleConvBot private
alpha. The canonical alpha runtime is local. Railway or another remote hosting
provider is not required for ALPHA-001.

## Runtime shape

Run exactly one bot application process together with:

1. PostgreSQL.
2. Redis.
3. SimpleConvBot itself.

Telegram uses long polling, so the local machine does not need a public HTTP
endpoint.

Exactly one bot process may use the alpha bot token at a time. Starting a second
copy with the same token can cause competing Telegram update consumption.

## Recommended local path: Docker Compose

The repository contains a bounded local bot profile in `compose.yaml`.

1. Copy the example environment file:

   ```text
   .env.example -> .env
   ```

2. Replace at minimum:

   ```text
   TELEGRAM_BOT_TOKEN=...
   POSTGRES_PASSWORD=...
   ```

   Keep the password in `DATABASE_URL` synchronized only when using the
   host-side Python mode described later. The Compose app profile constructs its
   database URL from the PostgreSQL service variables.

3. Build and start the full local alpha stack:

   ```bash
   docker compose --profile bot up --build
   ```

The app profile:

- builds the repository Dockerfile;
- waits for PostgreSQL and Redis health checks;
- runs `python -m simpleconvbot`;
- runs read-only with all Linux capabilities dropped and
  `no-new-privileges`;
- uses bounded tmpfs storage for the conversion workspace and `/tmp`;
- has explicit process, memory, and CPU limits;
- publishes no bot application port.

PostgreSQL and Redis bind only to loopback for optional host-side diagnostics.

Stop the stack with:

```bash
docker compose --profile bot down
```

The PostgreSQL named volume survives a normal stop. Use `down -v` only when
you intentionally want to discard local alpha database state.

## Alternative: bot process on the host

If the bot itself is started directly from Python, use Compose only for
PostgreSQL and Redis:

```bash
docker compose up -d postgres redis
```

Then install the project in a Python 3.12 environment and run:

```bash
python -m pip install -e .
python -m simpleconvbot
```

The Python process reads its settings from the process environment. It does
**not** implicitly load `.env`. Export the values from `.env.example` in the
same shell before starting the bot.

At minimum the runtime requires:

```text
TELEGRAM_BOT_TOKEN=<BotFather secret>
DATABASE_URL=postgresql+asyncpg://simpleconvbot:<password>@localhost:5432/simpleconvbot
REDIS_URL=redis://localhost:6379/0
```

Do not put the bot token in source files, issue comments, pull requests, logs,
or screenshots.

## Local alpha evidence identity

Start every evidence run from a clean, known revision.

Record:

- exact GitHub `main` commit SHA;
- execution mode: `compose` or `host-python`;
- for Compose mode, the local app image ID;
- start timestamp;
- aggregate operation/stage outcome data only.

Do not combine evidence from different commits or rebuilt images under one run
record.

Useful commands:

```bash
git rev-parse HEAD
docker compose --profile bot images
```

A remote deployment ID is not required for the current local alpha.

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

A failed periodic dependency probe is observable in diagnostics but does not by
itself terminate an already-running bot. Startup dependency health is
fail-closed.

All runtime log records pass through a final redacting formatter after exception
traceback formatting. Routine logs must still be reviewed during alpha.

## First launch verification

For each evidence run:

1. Confirm the local checkout is the intended exact `main` commit.
2. Confirm PostgreSQL and Redis are healthy.
3. Confirm startup completes schema initialization, recovery, initial retention
   sweep, and the initial `admin_diagnostic` with `health.ready=true`.
4. Confirm Telegram long polling stays active with exactly one bot process.
5. Open the alpha bot and send `/start`.
6. Verify navigation in both Russian and English Telegram locales.
7. Run at least one real file through each enabled family:
   - image conversion/compression;
   - PDF to images;
   - audio conversion;
   - video operation;
   - images-to-PDF collection;
   - PDF merge collection.
8. Exercise bounded failure paths:
   - unsupported input;
   - oversized input;
   - duplicate callback/update;
   - process restart during or around queued work.
9. Verify `admin_diagnostic` operation-stage aggregates move for the exercised
   operations and failure-class counts use only stable error codes.
10. Verify result delivery and cleanup without recording filenames, provider
    file references, user/chat IDs, message contents, tokens, database URLs, or
    Redis URLs.
11. Leave the bot running beyond one retention interval and verify that no
    unexplained stale workspace/session remains.

Use `docs/PRIVATE_ALPHA.md` as the acceptance record. Never check a real
Telegram item from repository CI alone.

## Restart semantics

At startup the runtime reconciles durable PostgreSQL state with Redis:

- Redis reserved/inflight queue entries are returned to the ready queue;
- durable `QUEUED` jobs are enqueue-safe again;
- `RECEIVED`, `VALIDATING`, `PROCESSING`, and `UPLOADING` jobs are treated
  as interrupted, their workspaces are cleaned, and they transition to
  `FAILED`;
- an interrupted `UPLOADING` job is not uploaded again because the prior
  Telegram request may already have succeeded before the process stopped;
- an unexpected queue-worker task failure terminates the application instead
  of leaving polling alive without a worker;
- after the local process is started again, the same startup reconciliation
  path runs;
- the user receives a bounded RU/EN restart message telling them to resend only
  if no result arrived.

A cleanup failure aborts startup before that interrupted job is marked failed,
so a subsequent start can retry cleanup rather than silently orphaning data.

## Local rollback

For a bad local revision:

1. Stop the bot.
2. Check out the previous known-good commit.
3. Rebuild the app image when using Compose.
4. Start the bot again.
5. Record both commit identities in the alpha evidence.

Do not manually edit PostgreSQL state as part of a routine application
rollback.

## Future remote hosting

A remote host may be added later, but it is outside the current ALPHA-001
runtime contract. When remote hosting becomes active, add a separate provider
runbook and deployment-identity evidence without replacing the local
Telegram-behavior evidence already required here.
