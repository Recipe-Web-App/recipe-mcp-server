# Stage 1: Build dependencies with uv
FROM python:3.13-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/bin/uv

WORKDIR /app

# Copy dependency files first for layer caching
COPY pyproject.toml uv.lock ./

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

RUN uv sync --frozen --no-dev

# Copy application source and migration files
COPY src/ src/
COPY alembic.ini ./
COPY migrations/ migrations/

# Stage 2: Runtime
FROM python:3.13-slim

WORKDIR /app

RUN useradd --create-home appuser && \
    mkdir -p /app/data && \
    chown appuser:appuser /app/data

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src
COPY --from=builder /app/alembic.ini /app/alembic.ini
COPY --from=builder /app/migrations /app/migrations

ENV PATH="/app/.venv/bin:$PATH"

USER appuser

EXPOSE 8000

CMD ["python", "-m", "recipe_mcp_server"]
