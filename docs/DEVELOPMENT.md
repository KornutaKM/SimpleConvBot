# Development

## Requirements

- Python 3.12
- Docker with Compose support for local PostgreSQL/Redis when those services are needed

The foundation intentionally has no production runtime dependencies yet. Runtime dependencies are added by the issue that first requires them.

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

On Windows, copy `.env.example` to `.env` using Explorer or PowerShell.

Replace all placeholder secrets in `.env`. The real `.env` file is ignored by Git.

## Quality gate

One command runs the same core checks as CI:

```bash
python scripts/verify.py
```

It executes:

1. Ruff formatting check
2. Ruff lint
3. strict mypy
4. pytest

Individual commands:

```bash
python -m ruff format --check .
python -m ruff check .
python -m mypy src tests
python -m pytest
```

## Local infrastructure

PostgreSQL and Redis are defined in `compose.yaml`.

After creating `.env`:

```bash
docker compose up -d postgres redis
docker compose ps
```

Stop services:

```bash
docker compose down
```

Remove development database data only when intentionally resetting local state:

```bash
docker compose down -v
```

## Containerized quality check

The development image is intentionally a verification image at this stage:

```bash
docker build -f docker/Dockerfile.dev -t simpleconvbot-dev .
docker run --rm simpleconvbot-dev
```

The application runtime container is deferred until CORE-001 defines the actual bot/application process.

## Configuration

`simpleconvbot.config.Settings` is the single foundation configuration model.

Rules:

- secrets come from environment/local secret injection
- token values are excluded from dataclass representation
- no `.env` loader is embedded in production code
- development tools may load `.env` externally later
- configuration must be validated before bot runtime starts

## Dependency policy

Dependencies belong in `pyproject.toml`.

Development tools are exact-pinned so the repository quality gate does not drift silently. Production dependencies should be introduced only by the issue that needs them, with compatibility and security review.

A generated lock file may be introduced when the runtime dependency graph becomes non-trivial; it should then become the CI installation source.

## Repository layout

```text
src/simpleconvbot/   application package
tests/               automated tests
scripts/             repository automation with bounded purpose
docs/                product/architecture/security/development docs
docs/adr/            architecture decision records
docker/              container definitions
.github/workflows/   CI
```

Conversion engines will receive dedicated modules/packages in their own issues. Do not place conversion logic in the Telegram gateway.
