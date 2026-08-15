# ── Build stage ───────────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# Install dependencies into an isolated prefix for clean copying
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Runtime stage ─────────────────────────────────────────────────────────────
FROM python:3.11-slim

# Non-root user for security
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser

WORKDIR /app

# Copy installed packages from the builder stage
COPY --from=builder /install /usr/local

# Copy application source
COPY --chown=appuser:appgroup . .

# Switch to non-root user
USER appuser

EXPOSE 8004

# Health check — the service must respond within 30 s on startup
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8004/docs')" || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8004", "--workers", "2"]
