"""POST /api/select-plan — Stage 5: Visualization asset generation."""

from __future__ import annotations

import asyncio
import json
import os

import httpx
import redis
from fastapi import APIRouter, HTTPException

from models.schemas import (
    BuildableZone,
    CadastralData,
    FloorPlanAlternative,
    FullDesignPackage,
    SelectPlanRequest,
    VisualizationAssets,
)
from utils.logger import get_logger

_logger = get_logger("router.design")

router = APIRouter()

_REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
_C02_ENDPOINT = os.getenv("COMPONENT02_ENDPOINT", "")


def _get_redis() -> redis.Redis:
    return redis.from_url(_REDIS_URL, decode_responses=True)


def _blueprint_description(alternative: FloorPlanAlternative) -> str:
    room_names = ", ".join(r.name for r in alternative.rooms)
    return (
        f"Technical 2D architectural floor plan showing {len(alternative.rooms)} rooms: "
        f"{room_names}. Total built area: {alternative.total_built_area_sqft:.0f} sqft. "
        f"Walls, door arcs, window symbols and dimension lines shown to scale."
    )


def _floorplan3d_description(alternative: FloorPlanAlternative) -> str:
    return (
        f"3D dollhouse isometric view of a {alternative.variant} layout with "
        f"{len(alternative.rooms)} rooms across {alternative.total_built_area_sqft:.0f} sqft "
        f"built area. Roof removed to reveal the interior room arrangement."
    )


@router.post("/select-plan")
async def select_plan(body: SelectPlanRequest) -> FullDesignPackage:
    """Run Stage 5 — generate visualization assets and return FullDesignPackage."""
    job_id = body.job_id
    variant = body.selected_variant

    r = _get_redis()

    cadastral_raw = r.get(f"job:{job_id}:cadastral")
    zone_raw = r.get(f"job:{job_id}:zone")
    alternatives_raw = r.get(f"job:{job_id}:alternatives")
    site_schema_raw = r.get(f"job:{job_id}:site_schema")
    user_req_raw = r.get(f"job:{job_id}:user_requirements")

    if not (cadastral_raw and zone_raw and alternatives_raw):
        raise HTTPException(
            status_code=404,
            detail=f"Job {job_id} state not found. Complete earlier stages first.",
        )

    cadastral = CadastralData.model_validate_json(cadastral_raw)
    zone = BuildableZone.model_validate_json(zone_raw)
    alternatives = [FloorPlanAlternative(**a) for a in json.loads(alternatives_raw)]
    site_schema = json.loads(site_schema_raw) if site_schema_raw else {}
    user_requirements = json.loads(user_req_raw) if user_req_raw else {}

    selected = next((a for a in alternatives if a.variant == variant), None)
    if selected is None:
        raise HTTPException(
            status_code=400,
            detail=f"Variant '{variant}' not found in job {job_id}.",
        )

    # Store selected alternative so /generate-video can retrieve room names later
    r.setex(
        f"job:{job_id}:selected_alternative",
        7200,
        json.dumps(selected.model_dump()),
    )

    # ---- Building Schema (SchemaSerialiser handles C02 fire-and-forget internally)
    building_schema: dict = {}
    try:
        from stages.stage4_renderer.schema_serialiser import SchemaSerialiser

        # SchemaSerialiser expects legacy field names — adapt FloorPlanAlternative model_dump
        floor_plan_dict = selected.model_dump()
        floor_plan_dict["layout_label"] = selected.variant
        floor_plan_dict["total_area_sqm"] = round(selected.total_built_area_sqft / 10.7639, 2)
        floor_plan_dict["quality_scores"] = selected.scores.model_dump()
        for room in floor_plan_dict.get("rooms", []):
            room["area_sqm"] = round(room.get("area_sqft", 0) / 10.7639, 2)

        building_schema = SchemaSerialiser().serialise(
            floor_plan=floor_plan_dict,
            site_schema=site_schema,
            buildable_zone=zone.model_dump(),
            user_requirements=user_requirements,
        )
        _logger.info("Job %s — Building Schema serialised", job_id)
    except Exception as exc:
        _logger.error("Job %s — SchemaSerialiser failed (non-blocking): %s", job_id, exc)

    # Async fire-and-forget to C02 (never blocks the response)
    if _C02_ENDPOINT:
        async def _post_c02() -> None:
            try:
                payload = {k: v for k, v in building_schema.items() if k != "_meta"}
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.post(_C02_ENDPOINT, json=payload)
                _logger.info("Job %s — C02 HTTP %s", job_id, resp.status_code)
            except Exception as exc:
                _logger.warning("Job %s — C02 POST failed (non-blocking): %s", job_id, exc)
        asyncio.create_task(_post_c02())

    # ---- Stage 5: image gen + text gen in parallel
    # Individual image failures return "" (handled inside generate_all_images).
    # Text failures are caught here — we always return a FullDesignPackage,
    # never a 500, so the frontend can display whatever assets succeeded.
    images: dict[str, str] = {
        "exterior": "", "interior": "", "blueprint_2d": "", "floorplan_3d": ""
    }
    walkthrough_script = ""
    shopping_list: list = []

    try:
        from stages.stage5_visualization.gemini_image_gen import generate_all_images
        from stages.stage5_visualization.gemini_text_gen import generate_all_text

        (images, (walkthrough_script, shopping_list)) = await asyncio.gather(
            generate_all_images(cadastral, zone, selected),
            generate_all_text(cadastral, zone, selected),
        )
        _logger.info("Job %s — Stage 5 visualization complete", job_id)
    except Exception as exc:
        _logger.error("Job %s — Stage 5 partial failure: %s", job_id, exc)
        # Continue — return whatever succeeded (images dict may have some filled)

    viz = VisualizationAssets(
        exterior_image_base64=images.get("exterior", ""),
        interior_image_base64=images.get("interior", ""),
        blueprint_2d_image_base64=images.get("blueprint_2d", ""),
        blueprint_2d_description=_blueprint_description(selected),
        floorplan_3d_image_base64=images.get("floorplan_3d", ""),
        floorplan_3d_description=_floorplan3d_description(selected),
        walkthrough_script=walkthrough_script,
        shopping_list=shopping_list,
    )

    return FullDesignPackage(
        job_id=job_id,
        cadastral_data=cadastral,
        buildable_zone=zone,
        selected_plan=selected,
        building_schema_json=building_schema,
        visualization_assets=viz,
        video=None,
    )
