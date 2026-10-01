# Public MVP production runbook

This runbook covers the provider-neutral requirements for RELEASE-001. The
private-alpha evidence is already complete; a public release still requires a
real continuously available production runtime and operator evidence.

The selected first-release provider is Railway. Use `docs/RAILWAY.md` together
with this provider-neutral contract.

## Production shape

Run exactly one SimpleConvBot polling application for the public bot token,
together with:

1. persistent PostgreSQL;
2. Redis;
3. the application image built from one exact reviewed `main` commit.

The bot uses Telegram long polling. A public inbound HTTP endpoint is not
required for the MVP.

Do not run a second polling process with the same bot token. A second process
can cause Telegram `getUpdates` conflicts and invalid production evidence.
The production runtime therefore uses a Redis-backed singleton lease around
startup recovery, worker execution, retention, diagnostics, and Telegram
polling. Lease loss is fail-closed.

## Required environment

Set production secrets through the hosting provider's secret store, never in the
repository:

- `APP_ENV=production`
- `TELEGRAM_BOT_TOKEN`
- `DATABASE_URL`
- `REDIS_URL`

Keep the current bounded runtime values unless a separately reviewed change
updates the contract:

- temporary workspace TTL: 3600 seconds;
- terminal job/update-receipt metadata TTL: 604800 seconds (7 days);
- retention sweep: 60 seconds;
- workspace quota: 64 MiB;
- per-user request rate: 60/minute;
- per-user active jobs: 3;
- global active jobs: 32.

The standard Telegram cloud Bot API has a separate 20 MiB input-download ceiling
enforced by the Telegram adapter before provider I/O.

## Deployment identity

Every production deployment record must capture:

- exact Git commit SHA;
- immutable image identifier/digest where the provider exposes one;
- deployment timestamp;
- provider/service identity;
- PostgreSQL and Redis service identity;
- whether exactly one bot polling process is active.

Never call a deployment successful only because an image built.

## Startup verification

A healthy start must:

1. initialize/verify the database schema;
2. connect to Redis;
3. execute startup recovery;
4. perform the initial retention sweep;
5. emit `admin_diagnostic` with PostgreSQL and Redis ready;
6. register RU/EN Telegram commands;
7. enter Telegram long polling;
8. keep the queue worker alive.

Startup dependency failure or incomplete recovery is a release blocker.

## Monitoring and alert conditions

The hosting/monitoring provider must surface at least these conditions:

- app process stopped or repeatedly restarting;
- Telegram polling conflict (`TelegramConflictError`);
- PostgreSQL or Redis not ready;
- startup recovery failure;
- cleanup/retention failure;
- sustained worker/validation/upload failure growth;
- repeated `telegram_download_failed` or `telegram_upload_failed`;
- no expected diagnostics from a supposedly running service.

Diagnostics and alerts must not include file names, file contents, Telegram
user/chat identifiers, bot tokens, or connection URLs.

Provider alert rules are external release evidence. Repository documentation
alone does not prove that alerts are active.

## Public smoke test

After deployment, use the public production bot and verify:

- `/start`, `/tools`, `/help`, and `/settings`;
- RU and EN Help/navigation;
- one image format conversion;
- one image compression preset;
- one image resize preset, including output-dimension verification;
- one PDF operation;
- one audio conversion;
- one video compression preset with a playable MP4 result;
- images-to-PDF with at least two images;
- PDF merge with at least two PDFs;
- unsupported input error;
- >20 MiB standard-Bot-API input gives the bounded oversized error;
- process remains healthy and cleanup/diagnostics continue.

Do not reuse private-alpha evidence as proof that a different production image
or host is healthy.

## Rollback

Maintain the previous known-good exact commit/image until the new production
revision passes smoke tests.

For rollback:

1. stop the faulty application instance;
2. deploy the previous known-good immutable image or exact commit;
3. keep the same durable PostgreSQL service;
4. keep Redis unless provider recovery requires replacement;
5. start exactly one polling application;
6. allow startup recovery to reconcile active jobs;
7. verify dependency health, polling, and diagnostics;
8. run a minimal `/start` + file-conversion smoke.

Do not restore temporary workspaces from backup and do not manually rewrite job
states as routine rollback procedure.

## Backups

Back up durable PostgreSQL metadata only according to the selected provider's
policy. Temporary conversion workspaces must not be included in backups.

Any production backup policy must be consistent with the public privacy notice.

## BotFather/public profile

Before release, configure the public bot profile outside the repository:

- name and username;
- concise description of supported file conversion;
- icon/avatar;
- commands/profile presentation as needed;
- a reachable privacy-notice location.

The running application also registers `/start`, `/tools`, `/help`, and
`/settings` in English and Russian.

## External release evidence

The following cannot be satisfied by CI alone:

- 24/7 production host selected and configured;
- production secrets installed;
- exact reviewed revision deployed;
- provider alerts enabled;
- BotFather public profile/privacy link configured;
- public production smoke completed;
- rollback drill completed or otherwise explicitly accepted by the operator.

Keep RELEASE-001 open until this evidence exists.
