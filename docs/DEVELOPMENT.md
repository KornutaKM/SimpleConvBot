# Development

## Requirements

- Python 3.12
- Docker with Compose support
- PostgreSQL and Redis for integration tests and runtime

## Bootstrap

From a fresh clone:

```bash
python -m venv .venv
```

Activate the environment.

Linux/macOS:

```bash
source .venv/bin/activate
```

PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Install the package and development tools:

```bash
python -m pip install -e ".[dev]"
```

Create local environment configuration:

```bash
cp .env.example .env
```

Replace all placeholder secrets in `.env`. The real `.env` file is ignored by Git.

## Fast quality gate

```bash
python scripts/verify.py
```

This runs formatting, linting, strict mypy, and all tests that do not require external infrastructure.

## Integration gate

Start PostgreSQL and Redis:

```bash
docker compose up -d postgres redis
```

Export/load the `DATABASE_URL` and `REDIS_URL` values from your local `.env`, then run:

```bash
python scripts/verify_integration.py
```

CI runs both the fast and integration gates.

## Runtime

After providing a real `TELEGRAM_BOT_TOKEN` and service URLs:

```bash
python -m simpleconvbot
```

Version check without starting Telegram polling:

```bash
python -m simpleconvbot --version
```

The current runtime creates the pre-alpha schema if it does not exist. Before schema evolution/public release, explicit database migrations must replace this bootstrap-only behavior.

## Containerized quality check

```bash
docker build -f docker/Dockerfile.dev -t simpleconvbot-dev .
docker run --rm simpleconvbot-dev
```

## Configuration rules

- secrets come from environment/local secret injection
- token values are excluded from dataclass representation
- no real `.env` file is committed
- runtime validates required settings before polling
- PostgreSQL is durable job/update authority
- Redis is an at-least-once queue transport

## Repository layout

```text
src/simpleconvbot/   application/control-plane package
tests/               unit and integration tests
scripts/             bounded repository verification commands
docs/                product/architecture/security/development docs
docs/adr/            architecture decision records
docker/              container definitions
.github/workflows/   CI
```

Conversion engines are added by their own issues. Conversion logic does not belong in the Telegram gateway.
