# ADR 0001 — Project layout and foundation tooling

Status: Accepted

## Context

SimpleConvBot will process hostile user files and later use multiple worker families. Before conversion code exists, the repository needs one predictable layout and one quality gate that can run locally and in CI.

The foundation should not prematurely pull in Telegram, database, queue, or conversion libraries before their owning issues define the integration.

## Decision

- Use Python 3.12 as the initial development/runtime language baseline.
- Use a `src/` package layout.
- Use `pyproject.toml` as the dependency and tool configuration source.
- Use Ruff for formatting/linting, mypy in strict mode, and pytest.
- Run all core checks through `python scripts/verify.py` locally and in GitHub Actions.
- Keep secrets in environment/local secret mechanisms; commit only `.env.example` placeholders.
- Use Docker Compose for local infrastructure services.
- Keep `main` stable and deliver substantive changes through focused PRs.
- Add production dependencies only when the issue that owns the functionality requires them.

## Consequences

Positive:

- repository checks are small and fast
- dependency ownership stays visible
- Telegram/conversion implementation is not coupled to bootstrap
- CI and local verification use the same command

Trade-offs:

- a lock file is deferred until runtime dependencies become non-trivial
- the development Docker image currently validates the repository rather than running the not-yet-defined application process
