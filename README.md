# Recipe MCP Server

A **production-ready Model Context Protocol (MCP) server** that provides LLM-powered clients with comprehensive recipe management, nutrition analysis, and meal planning capabilities.

Built as both a **learning showcase** demonstrating every MCP capability from the 2025-11-25 specification (23 distinct features) and a **production service** integrated into the `recipe-web-app` microservices ecosystem.

## Tech Stack

| Component       | Technology              | Purpose                                     |
| --------------- | ----------------------- | ------------------------------------------- |
| Framework       | FastMCP 3.1.1+          | MCP server with native OTel + schema gen    |
| Language        | Python 3.13+            | Latest stable, async/await                  |
| Runtime Manager | mise                    | Python version + task runner                |
| Package Manager | uv                      | Fast deterministic dependency resolution    |
| Database        | SQLite (aiosqlite)      | Zero-infrastructure, WAL mode               |
| Cache           | Redis 7+                | API response caching, session state         |
| ORM             | SQLAlchemy 2.0+         | Async support, repository pattern           |
| Validation      | Pydantic 2.10+          | Automatic JSON Schema for tool parameters   |
| Tracing         | OpenTelemetry + Jaeger  | Distributed tracing                         |
| Testing         | pytest + pytest-asyncio | Async test support with coverage            |

## Quickstart

```bash
# Prerequisites: mise (https://mise.jdx.dev)
git clone <repo> && cd recipe-mcp-server

# Install Python 3.13, uv, and all tools
mise install

# Install dependencies
uv sync

# Copy and configure environment
cp .env.example .env

# Run the server (stdio mode for Claude Desktop)
mise run dev
```

## Project Structure

```
recipe-mcp-server/
├── .mise.toml                        # mise: Python version + uv + task runner
├── pyproject.toml                    # uv: dependencies + build + tool config
├── lefthook.yml                      # Git hooks: lint, format, test, secrets
│
├── src/recipe_mcp_server/
│   ├── __init__.py
│   ├── __main__.py                   # Entry point: python -m recipe_mcp_server
│   ├── server.py                     # FastMCP app factory
│   ├── config.py                     # pydantic-settings configuration
│   ├── models/                       # Pydantic domain models
│   ├── db/                           # SQLite persistence (engine, tables, repos)
│   ├── cache/                        # Redis caching
│   ├── clients/                      # Downstream API clients
│   ├── services/                     # Business logic orchestration
│   ├── tools/                        # MCP Tool definitions
│   ├── resources/                    # MCP Resource definitions
│   ├── prompts/                      # MCP Prompt definitions
│   ├── sampling/                     # Server-initiated LLM sampling
│   └── elicitation/                  # User input collection
│
├── tests/
│   ├── conftest.py                   # Shared fixtures
│   ├── factories/                    # Test data factories
│   ├── unit/                         # Unit tests
│   ├── integration/                  # Integration tests (Redis)
│   └── e2e/                          # End-to-end protocol tests
│
├── migrations/                       # Alembic database migrations
└── docs/                             # Requirements and design docs
```

## Available Tasks

All tasks are run via `mise run <task>`:

| Task             | Description                                  |
| ---------------- | -------------------------------------------- |
| `dev`            | Run server locally (stdio mode)              |
| `dev-http`       | Run server locally (HTTP mode)               |
| `test`           | Run all tests                                |
| `test-unit`      | Run unit tests only                          |
| `test-integration` | Run integration tests (needs Redis)        |
| `test-e2e`       | Run end-to-end MCP protocol tests            |
| `test-coverage`  | Run tests with coverage report (85% min)     |
| `lint`           | Run all linters (ruff + mypy)                |
| `fmt`            | Auto-format code                             |
| `security`       | Run security checks (pip-audit + bandit)     |
| `db-migrate`     | Run Alembic migrations                       |
| `db-seed`        | Seed database with sample data               |
| `inspect`        | Launch MCP Inspector                         |
| `check`          | Run all checks (lint + test + security)      |
| `clean`          | Remove build artifacts and caches            |

## Contributing

1. Install [mise](https://mise.jdx.dev) and run `mise install`
2. Install dependencies: `uv sync`
3. Git hooks are managed by [lefthook](https://github.com/evilmartians/lefthook) and install automatically
4. Commits must follow [Conventional Commits](https://www.conventionalcommits.org/) format:
   ```
   feat(tools): add recipe search tool
   fix(db): handle concurrent WAL writes
   docs: update quickstart guide
   ```
5. All checks must pass before push: lint, type check, unit tests
