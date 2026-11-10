# ── Build stage: resolve the locked dependencies into /component02/.venv ──────
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /bin/uv

# Use the image's Python, compile bytecode once here, and copy (not hard-link)
# out of the cache mount.
ENV UV_PYTHON_DOWNLOADS=never \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# Same path as the runtime stage: venv scripts record it in their shebangs.
WORKDIR /component02
COPY pyproject.toml uv.lock .python-version ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

# ── Runtime stage: the venv and the app, no uv and no build cache ─────────────
FROM python:3.12-slim

# OpenMP runtime for XGBoost
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

ENV PATH="/component02/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1
WORKDIR /component02

COPY --from=builder /component02/.venv /component02/.venv
# .dockerignore keeps this to main.py, layers/, models/ and data/
COPY . .

# Only models/ and data/ need to be writable (retraining, rate imports), so
# chown just those instead of duplicating the whole tree in a new layer.
RUN useradd --create-home --shell /bin/bash appuser \
    && mkdir -p models data/ictad-rates \
    && chown -R appuser:appuser models data
USER appuser

EXPOSE 8002

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8002/health', timeout=5)" || exit 1

CMD ["uvicorn", "main:app", \
     "--host", "0.0.0.0", \
     "--port", "8002", \
     "--workers", "2", \
     "--log-level", "info"]
