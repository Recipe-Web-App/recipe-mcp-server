# CLAUDE.md

## Build

```bash
mise install              # Install Python 3.13, uv, and all tools
uv sync                   # Install all dependencies
uv sync --extra dev       # Install with dev dependencies
```

## Test

```bash
mise run test             # All tests
mise run test-unit        # Unit tests only
mise run test-integration # Integration tests (needs Redis)
mise run test-e2e         # E2E protocol tests
mise run test-coverage    # With coverage (85% min)
```

## Lint

```bash
mise run lint             # ruff check + ruff format --check + mypy
mise run fmt              # Auto-format
```

## Run

```bash
mise run dev              # stdio transport (for Claude Desktop)
mise run dev-http         # HTTP transport (port 8000)
```

## Docker

```bash
mise run docker-build     # Build image
mise run docker-up        # Start server + Redis + Jaeger
mise run docker-down      # Stop all services
```

Jaeger UI available at <http://localhost:16686> when running via Docker.

## Database

```bash
mise run db-migrate       # Run Alembic migrations
mise run db-seed          # Seed with sample data
```

## Key Conventions

- Python 3.13+, async/await throughout
- Conventional commits (`feat`/`fix`/`docs`/`chore`)
- Never commit directly to main -- create a feature branch and PR
- Never suppress linter findings -- fix the underlying issue
- All env vars use `RECIPE_MCP_` prefix (see `.env.example`)
- Use `uv` for all Python operations, never bare `python`/`pip`/`pytest`
- SQLite with WAL mode for storage, Redis for caching
- 85%+ test coverage required (branch coverage enabled)
