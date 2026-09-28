# Private Telegram deployment

This runbook is for the private UI prototype of SimpleConvBot. It is not the public-release procedure.

## Runtime shape

Deploy exactly three services in one Railway project:

1. SimpleConvBot application service from the GitHub repository.
2. PostgreSQL.
3. Redis.

The bot uses Telegram long polling, so the application service does not need a public HTTP domain.

Run exactly **one** application replica while polling is used. Multiple replicas with the same bot token would compete for Telegram updates.

## Application service

Source:

- GitHub repository: `KornutaKM/SimpleConvBot`
- branch: `main`

The repository root contains the production `Dockerfile`. Railway should build it automatically. The image starts:

```
python -m simpleconvbot
```

Do not override the command unless there is a specific operational reason.

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
```

If the database service names are not `Postgres` and `Redis`, use the actual Railway service names in the reference expressions.

`TELEGRAM_BOT_TOKEN` is a secret. Never commit it to this repository, an issue, a pull request, logs, or chat.

The application accepts provider PostgreSQL URLs beginning with `postgres://` or `postgresql://` and normalizes them to the SQLAlchemy asyncpg driver internally.

## PostgreSQL

Add Railway PostgreSQL to the same project.

The application currently bootstraps its pre-alpha schema at startup with SQLAlchemy metadata creation. Explicit database migrations are still required before schema evolution or public release.

Do not expose PostgreSQL publicly for this bot deployment.

## Redis

Add Railway Redis to the same project.

The bot uses Redis as its queue transport. Do not expose Redis publicly for this deployment.

## Deployment settings

Recommended private-prototype settings:

- replicas: 1
- restart policy: On Failure
- public networking: disabled
- GitHub auto-deploy: main branch only after CI succeeds

No `railway.toml` or `railway.json` is required for a new deployment. Keep provider project/service configuration in Railway until the project adopts Railway's current Infrastructure as Code workflow.

## First launch verification

After deployment:

1. Check application logs for successful PostgreSQL schema initialization.
2. Check that Redis ping succeeds and Telegram polling remains running.
3. Open `@KoxConv_bot`.
4. Send `/start`.
5. Verify:
   - home buttons render;
   - `Все инструменты` opens the category screen;
   - `Настройки` opens and returns correctly;
   - sending a photo produces image actions;
   - sending a PDF produces PDF actions;
   - operation buttons clearly identify prototype-only behavior where the engine is not wired end to end.

## Rollback

If a new deployment fails, roll back the application service to the previous known-good GitHub deployment. Do not change database contents manually as part of a routine application rollback.

If polling behaves unexpectedly, stop extra application replicas first and verify that only one instance is using the bot token.

## Secret rotation

If the Telegram token is ever exposed:

1. Revoke/regenerate it in BotFather.
2. Replace `TELEGRAM_BOT_TOKEN` in the hosting provider.
3. Redeploy/restart the application service.
4. Do not preserve the old token in repository history or incident notes.
