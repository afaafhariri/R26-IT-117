FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY alembic.ini .
COPY migrations ./migrations
COPY app ./app

# Non-root user for security
RUN useradd --create-home --shell /bin/bash appuser
USER appuser

EXPOSE 8080

# Bring authdb up to date, then serve. Migrations are idempotent, so this is
# safe on every start.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8080"]
