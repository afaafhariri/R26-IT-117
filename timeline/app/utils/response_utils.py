"""Small helpers for consistent API responses."""


def health_response() -> dict[str, str]:
    """Return the root health-check message."""

    return {"message": "Project Management & Timeline Prediction Backend is running"}
