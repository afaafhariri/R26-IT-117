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
    uv sync --locked --no-group train

# ── Runtime stage: the venv and the app, no uv and no build cache ─────────────
FROM python:3.12-slim

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1
WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
# .dockerignore drops notebooks and the training script; tests/ stays so the
# suite can run in the container (see README)
COPY . .

EXPOSE 5004

CMD ["python", "main.py"]
