"""POST /api/generate-video — user-triggered Veo video generation."""

from __future__ import annotations

import json
import os

import redis
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from models.schemas import FloorPlanAlternative, VideoAsset
from utils.logger import get_logger

_logger = get_logger("router.video")

router = APIRouter()

_REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")


def _get_redis() -> redis.Redis:
    return redis.from_url(_REDIS_URL, decode_responses=True)


class GenerateVideoRequest(BaseModel):
    job_id: str


@router.post("/generate-video")
async def generate_video(body: GenerateVideoRequest) -> VideoAsset:
    """Generate a walkthrough video for the selected plan (user-triggered, rate-limited)."""
    job_id = body.job_id
    r = _get_redis()

    cadastral_raw = r.get(f"job:{job_id}:cadastral")
    selected_raw = r.get(f"job:{job_id}:selected_alternative")

    if not cadastral_raw:
        raise HTTPException(
            status_code=404,
            detail=f"Job {job_id} not found.",
        )

    cadastral_data = json.loads(cadastral_raw)
    district = cadastral_data.get("district", "Colombo")
    orientation = cadastral_data.get("orientation", "North-facing")

    room_names: list[str] = []
    if selected_raw:
        try:
            alt = FloorPlanAlternative(**json.loads(selected_raw))
            room_names = [r.name for r in alt.rooms]
        except Exception as exc:
            _logger.warning("Could not load selected alternative for video: %s", exc)

    if not room_names:
        room_names = ["living room", "dining room", "kitchen", "bedroom", "bathroom"]

    _logger.info("Job %s — video generation requested (%s, %s)", job_id, district, orientation)

    try:
        from stages.stage5_visualization.gemini_video_gen import generate_video as _gen_video

        video_url, skip_reason = await _gen_video(district, orientation, room_names)
    except Exception as exc:
        _logger.error("Job %s — video generation exception: %s", job_id, exc)
        return VideoAsset(
            video_base64=None,
            skipped=True,
            skip_reason=f"Video generation error: {exc}",
        )

    if skip_reason:
        minutes_remaining: int | None = None
        if "minute" in skip_reason:
            import re
            m = re.search(r"(\d+) minute", skip_reason)
            if m:
                minutes_remaining = int(m.group(1))
        return VideoAsset(
            video_base64=None,
            skipped=True,
            skip_reason=skip_reason,
            minutes_until_available=minutes_remaining,
        )

    return VideoAsset(
        video_base64=video_url,
        skipped=False,
    )
