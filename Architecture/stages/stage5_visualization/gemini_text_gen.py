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

_MODEL = "gemini-3.6-flash"


def _call_text_sync(prompt: str, json_mode: bool = False) -> str:
    client = get_client()
    config = genai_types.GenerateContentConfig(
        response_mime_type="application/json" if json_mode else "text/plain",
        thinking_config=genai_types.ThinkingConfig(thinking_level="minimal"),
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
    """Parse JSON array from Gemini response using multiple strategies."""
    # Strip markdown fences
    text = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    text = re.sub(r"\s*```$", "", text).strip()

    # Strategy 1: direct parse
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return [ShoppingItem(**item) for item in data]
    except (json.JSONDecodeError, TypeError, ValueError):
        pass

    # Strategy 2: raw_decode scan for a JSON array
    decoder = json.JSONDecoder()
    for i, ch in enumerate(text):
        if ch == '[':
            try:
                obj, _ = decoder.raw_decode(text, i)
                if isinstance(obj, list) and obj:
                    return [ShoppingItem(**item) for item in obj]
            except (json.JSONDecodeError, TypeError, ValueError):
                continue

    _logger.error("Shopping list could not be parsed — raw (first 400): %s", raw[:400])
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
