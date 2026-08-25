"""POST /api/generate-floorplans + GET /api/floorplans/status/{job_id}"""

from __future__ import annotations

import json
import math
import os
from typing import Any

import redis
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from models.schemas import FloorPlanAlternative, FloorPlanScores, Room
from utils.logger import get_logger

_logger = get_logger("router.floorplans")

router = APIRouter()

_REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
_JOB_TTL = 7200

# Max width-to-height ratio for a single room in the displayed plan.
# The layout solver can produce very thin strips — clamp for readability.
_MAX_ROOM_ASPECT = 2.5


def _get_redis() -> redis.Redis:
    return redis.from_url(_REDIS_URL, decode_responses=True)


class UserRequirements(BaseModel):
    bedrooms: int = 3
    bathrooms: int = 2
    living_room: bool = True
    kitchen: bool = True
    dining_room: bool = True
    garage: bool = False
    style: str = "modern"
    floors: int = 1
    outdoor_features: list[str] = []   # garden, swimming_pool, patio, rooftop_terrace, balcony, outdoor_kitchen
    special_rooms: list[str] = []      # home_office, gym, home_theatre, prayer_room, maids_room, library, kids_playroom
    additional_notes: str = ""


class GenerateFloorplansRequest(BaseModel):
    job_id: str
    user_requirements: UserRequirements = UserRequirements()


def _build_room_types(req: UserRequirements) -> list[str]:
    """Convert individual room booleans + special rooms into the room_types list."""
    types: list[str] = []
    if req.living_room:
        types.append("living_room")
    if req.kitchen:
        types.append("kitchen")
    if req.dining_room:
        types.append("dining_room")
    if req.bedrooms >= 1:
        types.append("master_bedroom")
    for _ in range(req.bedrooms - 1):
        types.append("bedroom")
    for _ in range(req.bathrooms):
        types.append("bathroom")
    if req.garage:
        types.append("garage")
    # Special rooms added directly (home_office, gym, home_theatre, etc.)
    for room in req.special_rooms:
        types.append(room)
    return types


def _clamp_aspect(width: float, length: float) -> tuple[float, float]:
    """Clamp width:length ratio to _MAX_ROOM_ASPECT, preserving area."""
    if length <= 0:
        return width, width
    aspect = width / length
    if aspect > _MAX_ROOM_ASPECT:
        area = width * length
        width  = round(math.sqrt(area * _MAX_ROOM_ASPECT), 1)
        length = round(math.sqrt(area / _MAX_ROOM_ASPECT), 1)
    elif aspect < 1.0 / _MAX_ROOM_ASPECT:
        area = width * length
        length = round(math.sqrt(area * _MAX_ROOM_ASPECT), 1)
        width  = round(math.sqrt(area / _MAX_ROOM_ASPECT), 1)
    return width, length


def _raw_to_alternative(raw: dict, zone: dict) -> FloorPlanAlternative | None:
    """Convert the raw dict from the Celery task into a FloorPlanAlternative.

    Position AND size both come from the same normalized coordinate system
    (x_norm, y_norm, width_norm, height_norm) scaled by dim_ft = sqrt(buildable sqft).
    This guarantees the mini layout matches the solver's non-overlapping layout.
    """
    try:
        buildable_sqft = float(zone.get("buildable_area_sqft", 1000))
        # dim_ft is the approximate side length of a square with the same buildable area.
        # All normalized coords (0→1) map to (0→dim_ft) in feet.
        dim_ft = math.sqrt(buildable_sqft) if buildable_sqft > 0 else 30.0

        rooms: list[Room] = []
        for r in raw.get("rooms", []):
            w_norm = float(r.get("width_norm", 0.1))
            h_norm = float(r.get("height_norm", 0.1))
            x_norm = float(r.get("x_norm", 0.0))
            y_norm = float(r.get("y_norm", 0.0))

            # Consistent coordinate system: positions and sizes both scale by dim_ft.
            # This ensures rooms that don't overlap in norm space won't overlap on display.
            # NBC minimum sizes are enforced upstream in layout_solver.py, *before*
            # packing decides positions — enforcing them here instead (after packing)
            # would grow a room in place without adjusting its neighbors, reintroducing
            # the overlaps packing was supposed to eliminate.
            raw_w = w_norm * dim_ft
            raw_l = h_norm * dim_ft

            # Clamp unrealistic aspect ratios (e.g. corridor stretched to full row width)
            width_ft, length_ft = _clamp_aspect(raw_w, raw_l)
            area_sqft = width_ft * length_ft

            rooms.append(Room(
                name=r.get("name", "Room"),
                floor=int(r.get("floor", 1)),
                # Rounded to 2dp, not 1dp: position and length are rounded
                # independently, and 1dp granularity (up to 0.1ft error on
                # each) was enough to misalign rooms that solve_overlaps had
                # packed perfectly flush against each other, reopening
                # sub-square-foot overlaps between adjacent rooms.
                width_ft=round(width_ft, 2),
                length_ft=round(length_ft, 2),
                area_sqft=round(area_sqft, 1),
                position_x=round(x_norm * dim_ft, 2),
                position_y=round(y_norm * dim_ft, 2),
                adjacencies=r.get("adjacencies", []),
                has_window=bool(r.get("window_orientation")),
                has_door=True,
            ))

        # Scorer returns 0–1; ScoreBar expects 0–10 → multiply by 10.
        q: dict[str, Any] = raw.get("quality_scores", {})
        def _s(key: str, *fallbacks: str) -> float:
            for k in (key, *fallbacks):
                v = q.get(k)
                if v is not None:
                    return round(float(v) * 10, 1)
            return 0.0

        scores = FloorPlanScores(
            space_utilisation=_s("space_utilisation"),
            natural_light=_s("natural_light"),
            adjacency=_s("adjacency_quality", "adjacency"),
            ventilation=_s("ventilation_potential", "ventilation"),
            overall=_s("overall"),
        )

        total_sqft = sum(r.area_sqft for r in rooms) or (
            float(raw.get("total_area_sqm", 0)) * 10.7639
        )

        variant = raw.get("layout_label", "conservative")
        if variant not in ("conservative", "balanced", "creative"):
            variant = "conservative"

        description = (
            raw.get("layout_name")
            or raw.get("space_notes", "")[:300]
            or variant
        )

        return FloorPlanAlternative(
            variant=variant,
            temperature_used=float(raw.get("temperature", 0.4)),
            rooms=rooms,
            total_built_area_sqft=round(total_sqft, 2),
            scores=scores,
            validation_passed=bool(raw.get("is_valid", False)),
            description=description,
        )

    except Exception as exc:
        _logger.warning("Failed to convert plan to FloorPlanAlternative: %s", exc)
        return None


@router.post("/generate-floorplans")
async def generate_floorplans(body: GenerateFloorplansRequest):
    """Dispatch Stage 3 async Celery task and return immediately."""
    job_id = body.job_id

    r = _get_redis()
    zone_raw = r.get(f"job:{job_id}:zone")
    if not zone_raw:
        raise HTTPException(
            status_code=404,
            detail=f"Job {job_id} not found. Run /process-cadastral first.",
        )

    cadastral_raw = r.get(f"job:{job_id}:cadastral")
    buildable_zone = json.loads(zone_raw)
    cadastral = json.loads(cadastral_raw) if cadastral_raw else {}

    req = body.user_requirements
    room_types = _build_room_types(req)
    floors = req.floors or int(buildable_zone.get("max_floors", 1))

    user_requirements = {
        "room_types": room_types,
        "room_count": len(room_types),
        "bedrooms": req.bedrooms,
        "bathrooms": req.bathrooms,
        "garage": req.garage,
        "floors": floors,
        "style": req.style,
        "budget_tier": "medium",
        "district": cadastral.get("district", "Ampara"),
        "orientation": cadastral.get("orientation", "North-facing"),
        "is_coastal": False,
        "outdoor_features": req.outdoor_features,
        "special_rooms": req.special_rooms,
        "additional_notes": req.additional_notes,
    }

    from tasks.celery_app import generate_floor_plan_async
    task = generate_floor_plan_async.delay(buildable_zone, user_requirements)
    r.setex(f"job:{job_id}:celery_task_id", _JOB_TTL, task.id)
    r.setex(f"job:{job_id}:user_requirements", _JOB_TTL, json.dumps(user_requirements))

    _logger.info("Job %s — Celery task dispatched: %s | rooms=%s floors=%d",
                 job_id, task.id, room_types, floors)
    return {"job_id": job_id, "status": "processing"}


@router.get("/floorplans/status/{job_id}")
async def get_floorplan_status(job_id: str):
    """Poll for Stage 3 result."""
    r = _get_redis()
    task_id = r.get(f"job:{job_id}:celery_task_id")
    if not task_id:
        raise HTTPException(
            status_code=404,
            detail=f"No floor plan task found for job {job_id}.",
        )

    from celery.result import AsyncResult
    from tasks.celery_app import celery_app

    result = AsyncResult(task_id, app=celery_app)

    if result.state in ("PENDING", "STARTED"):
        return {"status": "processing", "alternatives": None}

    if result.state == "FAILURE":
        _logger.error("Job %s — Celery task failed: %s", job_id, result.info)
        return {"status": "failed", "alternatives": None, "error": str(result.info)}

    if result.state == "SUCCESS":
        raw_list = result.result

        if isinstance(raw_list, list) and raw_list and "error" in raw_list[0]:
            return {"status": "failed", "alternatives": None, "error": raw_list[0]["error"]}

        zone_raw = r.get(f"job:{job_id}:zone")
        zone = json.loads(zone_raw) if zone_raw else {}

        alternatives = []
        for raw in (raw_list if isinstance(raw_list, list) else []):
            alt = _raw_to_alternative(raw, zone)
            if alt:
                alternatives.append(alt)

        r.setex(
            f"job:{job_id}:alternatives",
            _JOB_TTL,
            json.dumps([a.model_dump() for a in alternatives]),
        )
        _logger.info("Job %s — %d alternatives ready", job_id, len(alternatives))
        return {"status": "complete", "alternatives": alternatives}

    return {"status": result.state.lower(), "alternatives": None}
