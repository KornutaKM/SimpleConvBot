# RELEASE-001 — Public MVP checklist

This checklist separates repository evidence from external production evidence.
Do not convert an unchecked external item to PASS from CI or documentation.

## Repository-ready gates

- [x] ALPHA-001 completed with RU/EN manual review and all machine runtime gates.
- [x] Security release controls are represented in code/CI and hardened-container
  smoke.
- [x] In-bot RU/EN Help describes enabled operations and current limits.
- [x] Standard Telegram cloud download limit is rejected before provider I/O.
- [x] Unsupported/oversized inputs have bounded user-facing errors.
- [x] Restart fail-closed behavior was proven during ALPHA-001.
- [x] Public privacy notice exists and distinguishes files from operational
  metadata.
- [x] Provider-neutral production, monitoring, smoke, and rollback runbook
  exists.
- [x] `/help` is part of the runtime Telegram command set.
- [x] Canonical fallback/RU Telegram profile copy and an explicit dry-run/apply
  procedure exist in `docs/BOT_PROFILE.md`.
- [x] First public hosting path selected: Railway; provider-specific deployment
  and rollback runbook exists in `docs/RAILWAY.md`.
- [x] Redis-backed singleton runtime lease prevents concurrent owned runtime work
  during deployment overlap and fails closed on lease loss.

## Privacy/retention decision

- [x] PostgreSQL terminal job rows and Telegram update receipts have a bounded
  seven-day age-based retention policy; active jobs are preserved.
- [ ] Confirm the selected production backup retention does not capture temporary
  workspaces and matches `docs/PRIVACY.md`.

## External production gates

- [ ] Configure the selected Railway production project/environment.
- [ ] Provision persistent PostgreSQL and Redis.
- [ ] Install production secrets through the provider secret store.
- [ ] Deploy one exact reviewed `main` commit/image.
- [ ] Confirm exactly one polling app instance uses the public bot token.
- [ ] Confirm startup health/recovery/retention/diagnostics are healthy.
- [ ] Enable provider alerts for the conditions in `docs/PRODUCTION.md`.
- [ ] Configure BotFather name/description/avatar and a reachable privacy link.
- [ ] Run the production smoke matrix in `docs/PRODUCTION.md`, including image compression/resize and a video compression preset.
- [ ] Verify production cleanup after success and failure.
- [ ] Verify the >20 MiB transport rejection in the production bot.
- [ ] Perform or explicitly approve a rollback drill using the previous
  known-good image/revision.

## Production smoke manifest

Use `docs/PRODUCTION_SMOKE.md` for the exhaustive production matrix. Initialize
the local manifest from the exact production review:

```bash
python scripts/production_smoke.py init \
  --review .production-review.json \
  --output .production-smoke.json
```

Mark each check individually after real observation. There is intentionally no
bulk `all` command. A complete manifest can be applied back to the production
review only through `production_smoke.py apply-review`, which is limited to the
four smoke-related release checks.

## Final approval

- [ ] No open Security Release Gate violation.
- [ ] No unexplained production failure class.
- [ ] Public privacy wording matches the deployed behavior.
- [ ] All advertised operations have observed production paths.
- [ ] RELEASE-001 operator review completed.


## Production acceptance manifest

Keep the final production attestation in a local, uncommitted
`.production-review.json`. Initialize it only after the exact production
deployment exists:

```bash
python scripts/production_review.py init \
  --output .production-review.json \
  --provider railway \
  --deployment-id <railway-deployment-id> \
  --runtime-id <immutable-image-or-runtime-id>
```

The manifest is bound to the current full Git commit. If the checkout moves to a
different commit, the CLI refuses to mutate the old review and
`release_ready` becomes false.

Mark one check only after the matching external evidence has actually been
observed:

```bash
python scripts/production_review.py mark \
  --input .production-review.json \
  --check startup_health_confirmed \
  --status pass
```

Show the current state:

```bash
python scripts/production_review.py show --input .production-review.json
```

The final release gate is:

```bash
python scripts/production_review.py show \
  --input .production-review.json \
  --require-ready

echo $?
```

Exit `0` means every production/final-approval check is PASS on the exact
bound commit and deployment. Exit `2` means at least one item is pending,
failed, or stale. Do not commit the manifest or raw production logs.


## Machine evidence from production logs

For the exact Railway deployment under review, run
`scripts/production_evidence.py` as documented in `docs/RAILWAY.md`.
A machine-ready result can populate exactly three manifest checks, but only
through the explicit `import-machine` command on the same commit-bound review:

- `exact_revision_deployed`;
- `singleton_polling_confirmed`;
- `startup_health_confirmed`.

```bash
python scripts/production_review.py import-machine \
  --input .production-review.json \
  --evidence production-runtime.log
```

The command reparses the raw log against the review's exact commit and deployment
binding. It refuses stale checkout state, deployment mismatch, incomplete startup
evidence, or an observed polling conflict. It cannot mark any other gate.

Production smoke, cleanup-after-real-user-flows, backup configuration, provider
alerts, BotFather configuration, rollback, privacy/failure/security review, and
final operator approval still require their specific external evidence.
