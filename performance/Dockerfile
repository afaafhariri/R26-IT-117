# ── Stage 1: builder ───────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

# Build-time dependencies for confluent-kafka and psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        g++ \
        librdkafka-dev \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Stage 2: runtime ───────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

# Runtime libraries only
RUN apt-get update && apt-get install -y --no-install-recommends \
        librdkafka1 \
        libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Non-root user for security
RUN groupadd -r appuser && useradd -r -g appuser appuser

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application source
COPY --chown=appuser:appuser . .

# Pre-create models directory so the app can load weights at runtime
RUN mkdir -p /app/models && chown appuser:appuser /app/models

USER appuser

# Expose FastAPI port
EXPOSE 8003

# Health-check hits the docs endpoint (lightweight)
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8003/docs')"

# Run with Uvicorn; workers can be tuned via env var
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port 8003 --workers ${UVICORN_WORKERS:-2} --log-level info"]
