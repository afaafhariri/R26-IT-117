"""Stage 5 — text generation via gemini-2.5-flash.

Generates:
  1. Walkthrough script (plain text, 250–350 words)
  2. Shopping list (JSON array of ShoppingItem)
"""

from __future__ import annotations

import asyncio
import json
import re

from google.genai import types as genai_types

from models.schemas import BuildableZone, CadastralData, FloorPlanAlternative, ShoppingItem
from stages.stage5_visualization.prompt_templates import (
    shopping_list_prompt,
    walkthrough_script_prompt,
)
from utils.gemini_client import get_client
from utils.logger import get_logger

_logger = get_logger("gemini_text_gen")

_MODEL = "gemini-2.5-flash"


def _call_text_sync(prompt: str, json_mode: bool = False) -> str:
    client = get_client()
    config = genai_types.GenerateContentConfig(
        response_mime_type="application/json" if json_mode else "text/plain",
    )
    response = client.models.generate_content(
        model=_MODEL,
        contents=prompt,
        config=config,
    )
    return response.text


async def _call_text(prompt: str, label: str, json_mode: bool = False) -> str:
    _logger.info("Generating %s (json_mode=%s)", label, json_mode)
    result = await asyncio.get_event_loop().run_in_executor(
        None, _call_text_sync, prompt, json_mode
    )
    _logger.info("%s generated (%d chars)", label, len(result))
    return result


def _parse_shopping_list(raw: str) -> list[ShoppingItem]:
    """Parse JSON from Gemini response, falling back to regex extraction."""
    try:
        data = json.loads(raw)
        return [ShoppingItem(**item) for item in data]
    except (json.JSONDecodeError, TypeError, ValueError):
        _logger.warning("JSON parse failed on shopping list — attempting regex extraction")

    # Regex fallback: find JSON array anywhere in the response
    match = re.search(r"\[.*\]", raw, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
            return [ShoppingItem(**item) for item in data]
        except Exception as exc:
            _logger.error("Regex JSON extraction also failed: %s", exc)

    # Last resort: return a single placeholder so the pipeline doesn't crash
    _logger.error("Shopping list could not be parsed — returning empty list")
    return []


async def generate_walkthrough(
    cadastral: CadastralData,
    zone: BuildableZone,
    alternative: FloorPlanAlternative,
) -> str:
    prompt = walkthrough_script_prompt(
        district=cadastral.district,
        land_area_perches=cadastral.land_area_perches,
        orientation=cadastral.orientation,
        road_access_type=cadastral.road_access_type,
        rooms=alternative.rooms,
        total_built_area_sqft=alternative.total_built_area_sqft,
        bcr_value=zone.bcr_value,
    )
    return await _call_text(prompt, "walkthrough_script", json_mode=False)


async def generate_shopping_list(
    alternative: FloorPlanAlternative,
) -> list[ShoppingItem]:
    prompt = shopping_list_prompt(rooms=alternative.rooms)
    raw = await _call_text(prompt, "shopping_list", json_mode=True)
    return _parse_shopping_list(raw)


async def generate_all_text(
    cadastral: CadastralData,
    zone: BuildableZone,
    alternative: FloorPlanAlternative,
) -> tuple[str, list[ShoppingItem]]:
    """Runs walkthrough and shopping list generation in parallel."""
    script, shopping = await asyncio.gather(
        generate_walkthrough(cadastral, zone, alternative),
        generate_shopping_list(alternative),
    )
    return script, shopping
