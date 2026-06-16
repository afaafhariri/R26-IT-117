"""POST /api/generate-floorplans + GET /api/floorplans/status/{job_id}"""

from __future__ import annotations

import json
import os

import redis
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from models.schemas import FloorPlanAlternative
from utils.logger import get_logger

_logger = get_logger("router.floorplans")

router = APIRouter()

_REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
_JOB_TTL = 7200


def _get_redis() -> redis.Redis:
    return redis.from_url(_REDIS_URL, decode_responses=True)


class GenerateFloorplansRequest(BaseModel):
    job_id: str


@router.post("/generate-floorplans")
async def generate_floorplans(body: GenerateFloorplansRequest):
    """Dispatch Stage 3 async Celery task and return immediately."""
    job_id = body.job_id

    r = _get_redis()
    site_schema_raw = r.get(f"job:{job_id}:site_schema")
    if not site_schema_raw:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found. Run /process-cadastral first.")

    site_schema = json.loads(site_schema_raw)

    # Import Celery task lazily
    from tasks.celery_app import generate_floor_plan_task

    task = generate_floor_plan_task.delay(site_schema)

    # Store the Celery task ID so the status endpoint can retrieve the result
    r.setex(f"job:{job_id}:celery_task_id", _JOB_TTL, task.id)

    _logger.info("Job %s — Celery task dispatched: %s", job_id, task.id)
    return {"job_id": job_id, "status": "processing"}


@router.get("/floorplans/status/{job_id}")
async def get_floorplan_status(job_id: str):
    """Poll for Stage 3 result."""
    r = _get_redis()
    task_id = r.get(f"job:{job_id}:celery_task_id")
    if not task_id:
        raise HTTPException(status_code=404, detail=f"No floor plan task found for job {job_id}.")

    from celery.result import AsyncResult
    from tasks.celery_app import celery_app

    result = AsyncResult(task_id, app=celery_app)

    if result.state == "PENDING" or result.state == "STARTED":
        return {"status": "processing", "alternatives": None}

    if result.state == "FAILURE":
        _logger.error("Job %s — Celery task failed: %s", job_id, result.info)
        return {"status": "failed", "alternatives": None, "error": str(result.info)}

    if result.state == "SUCCESS":
        raw = result.result
        # raw is the dict returned by generate_floor_plan_task
        alternatives_raw = raw.get("alternatives", [])
        alternatives = [FloorPlanAlternative(**a) for a in alternatives_raw]

        # Persist alternatives in Redis for /select-plan to load
        r.setex(
            f"job:{job_id}:alternatives",
            _JOB_TTL,
            json.dumps([a.model_dump() for a in alternatives]),
        )
        _logger.info("Job %s — %d alternatives ready", job_id, len(alternatives))
        return {"status": "complete", "alternatives": alternatives}

    return {"status": result.state.lower(), "alternatives": None}
