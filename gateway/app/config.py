"""Gateway settings, read once from the environment (and gateway/.env if present)."""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def _default_services() -> dict[str, str]:
    return {
        "c01": "http://localhost:8001",
        "c02": "http://localhost:8002",
        "c03": "http://localhost:8000",
        "c04": "http://localhost:5004",
    }


@dataclass(frozen=True)
class Settings:
    # Base URL of each component service, keyed by the name used in
    # /api/<name>/... Defaults are the local dev ports from the root README;
    # docker-compose overrides them with internal hostnames.
    services: dict[str, str] = field(default_factory=_default_services)
    # Read timeout for a proxied request. C01's plan processing and Gemini
    # renders can take minutes, so this is deliberately generous.
    upstream_timeout_seconds: float = 300.0

    # authdb, as the gateway's own login (SQLAlchemy URL, psycopg driver).
    database_url: str = ""

    # Where the planner UI is served. Links in emails point here.
    app_base_url: str = "http://localhost:5173"
    # Origins allowed to send state-changing requests (the CSRF defence).
    allowed_origins: frozenset[str] = frozenset(
        {"http://localhost:5173", "http://localhost:8080"}
    )
    # Secure cookies are only sent over HTTPS. Chrome and Firefox also accept
    # them on http://localhost; Safari does not, hence the switch for local dev.
    cookie_secure: bool = True

    # How email is delivered: "resend" (production), "smtp" (Mailpit in local
    # dev) or "console" (written to the log, for when neither is available).
    email_backend: str = "console"
    email_from: str = "Construction Planner <no-reply@localhost>"
    resend_api_key: str = ""
    smtp_host: str = "localhost"
    smtp_port: int = 1025


def load_settings() -> Settings:
    services = {
        name: os.getenv(f"{name.upper()}_URL", url).rstrip("/")
        for name, url in _default_services().items()
    }
    origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:8080")
    return Settings(
        services=services,
        upstream_timeout_seconds=float(os.getenv("UPSTREAM_TIMEOUT_SECONDS", "300")),
        database_url=os.getenv("DATABASE_URL", ""),
        app_base_url=os.getenv("APP_BASE_URL", "http://localhost:5173").rstrip("/"),
        allowed_origins=frozenset(o.strip() for o in origins.split(",") if o.strip()),
        cookie_secure=os.getenv("COOKIE_SECURE", "true").strip().lower() != "false",
        email_backend=os.getenv("EMAIL_BACKEND", "console").strip().lower(),
        email_from=os.getenv("EMAIL_FROM", "Construction Planner <no-reply@localhost>"),
        resend_api_key=os.getenv("RESEND_API_KEY", ""),
        smtp_host=os.getenv("SMTP_HOST", "localhost"),
        smtp_port=int(os.getenv("SMTP_PORT", "1025")),
    )
