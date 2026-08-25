"""Application configuration for the project management timeline backend."""

import os
from dataclasses import dataclass, field
from functools import lru_cache


@dataclass
class Settings:
    """Environment-driven settings for local development and Docker."""

    app_name: str = "Project Management & Timeline Prediction Backend"
    app_version: str = "1.0.0"
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./timeline_predictions.db")
    allowed_origins: list[str] = field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://localhost:5173",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:5173",
            "null",
        ]
    )


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""

    return Settings()
