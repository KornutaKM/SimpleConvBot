# Contributing

## Branch and review model

- `main` is the stable integration branch.
- Substantial work is done on a focused branch.
- One pull request should represent one coherent issue or gate.
- Conversion behavior must not be added as an unreviewed one-off script.
- Architecture/security contract changes should be explicit in the same PR or a preceding ADR.

## Local checks

Run the same quality gate as CI:

```bash
python scripts/verify.py
```

See `docs/DEVELOPMENT.md` for bootstrap instructions.

## Secrets

Never commit:

- Telegram bot tokens
- production database credentials
- private keys
- API tokens
- real `.env` files

Only placeholders belong in `.env.example`.

## Architecture decisions

Changes that materially alter boundaries, state semantics, security assumptions, storage, execution, or dependencies should add an ADR under `docs/adr/`.

## Definition of done

A change is not done because it works once. It should include the tests, failure behavior, documentation, and observability appropriate to its risk.
