"""Shared Google GenAI client — supports both API key and Vertex AI (service account)."""

import os

from google import genai

from utils.logger import get_logger

_logger = get_logger("gemini_client")

_client: genai.Client | None = None


def get_client() -> genai.Client:
    global _client
    if _client is None:
        use_vertex = os.getenv("USE_VERTEX_AI", "false").lower() == "true"

        if use_vertex:
            project = os.getenv("GOOGLE_CLOUD_PROJECT", "inner-legacy-492011-b4")
            location = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
            _client = genai.Client(
                vertexai=True,
                project=project,
                location=location,
            )
            _logger.info(
                "Gemini client initialised (Vertex AI, project=%s, location=%s)",
                project, location,
            )
        else:
            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                raise RuntimeError("GEMINI_API_KEY is not set in environment")
            _client = genai.Client(api_key=api_key)
            _logger.info("Gemini client initialised (API key)")

    return _client
