"""Shared Google GenAI client initialised once from GEMINI_API_KEY."""

import os

from google import genai

from utils.logger import get_logger

_logger = get_logger("gemini_client")

_client: genai.Client | None = None


def get_client() -> genai.Client:
    global _client
    if _client is None:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not set in environment")
        _client = genai.Client(api_key=api_key)
        _logger.info("Gemini client initialised")
    return _client
