"""Stage 5 — image generation via imagen-4.0-generate-001.

Generates 4 images in parallel:
  1. Exterior photorealistic render  (16:9)
  2. Interior photorealistic render  (16:9)
  3. 2D blueprint floor plan         (4:3)
  4. 3D dollhouse floor plan         (16:9)

All responses are returned as base64-encoded PNG strings.
"""

from __future__ import annotations

import asyncio
import base64
from typing import Any

from google.genai import types as genai_types

from models.schemas import BuildableZone, CadastralData, FloorPlanAlternative
from stages.stage5_visualization.prompt_templates import (
    blueprint_2d_prompt,
    exterior_prompt,
    floorplan_3d_prompt,
    interior_prompt,
)
from utils.gemini_client import get_client
from utils.logger import get_logger

_logger = get_logger("gemini_image_gen")

_MODEL = "imagen-4.0-generate-001"


def _infer_floors(total_sqft: float, buildable_sqft: float) -> int:
    if buildable_sqft > 0 and total_sqft / buildable_sqft > 1.3:
        return 2
    return 1


def _find_living_room(alternative: FloorPlanAlternative) -> Any | None:
    for r in alternative.rooms:
        if "living" in r.name.lower():
            return r
    return alternative.rooms[0] if alternative.rooms else None


def _generate_image_sync(prompt: str, aspect_ratio: str) -> str:
    """Blocking imagen call — runs in a thread pool to stay non-blocking."""
    client = get_client()
    response = client.models.generate_images(
        model=_MODEL,
        prompt=prompt,
        config=genai_types.GenerateImagesConfig(
            number_of_images=1,
            aspect_ratio=aspect_ratio,
            output_mime_type="image/png",
        ),
    )
    image_bytes = response.generated_images[0].image.image_bytes
    return base64.b64encode(image_bytes).decode("utf-8")


async def _generate_image(prompt: str, aspect_ratio: str, label: str) -> str:
    _logger.info("Generating %s image (aspect=%s)", label, aspect_ratio)
    try:
        result = await asyncio.get_event_loop().run_in_executor(
            None, _generate_image_sync, prompt, aspect_ratio
        )
        _logger.info("%s image generated (%d bytes base64)", label, len(result))
        return result
    except Exception as exc:
        _logger.error("Failed to generate %s image: %s", label, exc)
        raise


async def generate_all_images(
    cadastral: CadastralData,
    zone: BuildableZone,
    alternative: FloorPlanAlternative,
) -> dict[str, str]:
    """Runs all 4 imagen calls in parallel.

    Returns:
        dict with keys: exterior, interior, blueprint_2d, floorplan_3d
        Values are base64 PNG strings.
    """
    living = _find_living_room(alternative)
    floors = _infer_floors(alternative.total_built_area_sqft, zone.buildable_area_sqft)

    ext_prompt = exterior_prompt(
        district=cadastral.district,
        land_area_sqft=cadastral.land_area_sqft,
        orientation=cadastral.orientation,
        road_access_type=cadastral.road_access_type,
        total_built_area_sqft=alternative.total_built_area_sqft,
        buildable_area_sqft=zone.buildable_area_sqft,
        floors=floors,
    )
    int_prompt = interior_prompt(
        living_room_width=living.width_ft if living else 14,
        living_room_length=living.length_ft if living else 18,
        adjacencies=living.adjacencies if living else [],
        orientation=cadastral.orientation,
    )
    bp_prompt = blueprint_2d_prompt(
        rooms=alternative.rooms,
        total_built_area_sqft=alternative.total_built_area_sqft,
    )
    fp3d_prompt = floorplan_3d_prompt(rooms=alternative.rooms)

    exterior, interior, blueprint_2d, floorplan_3d = await asyncio.gather(
        _generate_image(ext_prompt, "16:9", "exterior"),
        _generate_image(int_prompt, "16:9", "interior"),
        _generate_image(bp_prompt, "4:3", "blueprint_2d"),
        _generate_image(fp3d_prompt, "16:9", "floorplan_3d"),
    )

    return {
        "exterior": exterior,
        "interior": interior,
        "blueprint_2d": blueprint_2d,
        "floorplan_3d": floorplan_3d,
    }
