# ── Build stage: resolve the locked dependencies into /app/.venv ──────────────
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /bin/uv

# Use the image's Python, compile bytecode once here, and copy (not hard-link)
# out of the cache mount.
ENV UV_PYTHON_DOWNLOADS=never \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

# ── Runtime stage: the venv and the app, no uv and no build cache ─────────────
FROM python:3.12-slim

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1
WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY alembic.ini .
COPY migrations ./migrations
COPY app ./app

RUN useradd --create-home --shell /bin/bash appuser
USER appuser

EXPOSE 8080

# Bring authdb up to date, then serve. Migrations are idempotent, so this is
# safe on every start.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8080"]
