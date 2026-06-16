"""POST /api/select-plan — Stage 4 → Stage 5 → Stage 6 → FullDesignPackage."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import httpx
import redis
from fastapi import APIRouter, HTTPException

from models.schemas import (
    BuildableZone,
    CadastralData,
    FloorPlanAlternative,
    FullDesignPackage,
    SelectPlanRequest,
    StageLogEntry,
)
from stages.stage6_packager.package_assembler import assemble
from utils.logger import get_logger

_logger = get_logger("router.design")

router = APIRouter()

_REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
_TEMP_DIR = Path(os.getenv("TEMP_FILES_DIR", "./tmp"))
_C02_ENDPOINT = os.getenv("COMPONENT02_ENDPOINT", "")


def _get_redis() -> redis.Redis:
    return redis.from_url(_REDIS_URL, decode_responses=True)


def _log(stage: str, message: str) -> StageLogEntry:
    return StageLogEntry(
        stage=stage,
        message=message,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@router.post("/select-plan", response_model=FullDesignPackage)
async def select_plan(body: SelectPlanRequest) -> FullDesignPackage:
    """Run Stage 4 + Stage 5 + Stage 6 and return the FullDesignPackage."""

    job_id = body.job_id
    variant = body.selected_variant
    stage_log: list[StageLogEntry] = []

    # ------------------------------------------------------------------ load state
    r = _get_redis()

    cadastral_raw = r.get(f"job:{job_id}:cadastral")
    zone_raw = r.get(f"job:{job_id}:zone")
    alternatives_raw = r.get(f"job:{job_id}:alternatives")

    if not (cadastral_raw and zone_raw and alternatives_raw):
        raise HTTPException(status_code=404, detail=f"Job {job_id} state not found. Complete earlier stages first.")

    cadastral = CadastralData.model_validate_json(cadastral_raw)
    zone = BuildableZone.model_validate_json(zone_raw)
    alternatives = [FloorPlanAlternative(**a) for a in json.loads(alternatives_raw)]

    selected = next((a for a in alternatives if a.variant == variant), None)
    if selected is None:
        raise HTTPException(status_code=400, detail=f"Variant '{variant}' not found in job {job_id}.")

    stage_log.append(_log("stage4", "Starting SVG and PDF rendering."))

    # ------------------------------------------------------------------ Stage 4
    try:
        from stages.stage1_extraction.schema_assembler import SchemaAssembler
        from stages.stage4_renderer.pdf_renderer import PDFRenderer
        from stages.stage4_renderer.schema_serialiser import SchemaSerialiser
        from stages.stage4_renderer.svg_renderer import SVGRenderer

        site_schema = json.loads(r.get(f"job:{job_id}:site_schema") or "{}")

        _TEMP_DIR.mkdir(parents=True, exist_ok=True)
        svg_path = _TEMP_DIR / f"{job_id}_floor_plan.svg"
        pdf_path = _TEMP_DIR / f"{job_id}_report.pdf"

        svg_renderer = SVGRenderer()
        svg_renderer.render(selected.model_dump(), str(svg_path))
        stage_log.append(_log("stage4", "SVG floor plan rendered."))

        pdf_renderer = PDFRenderer()
        pdf_renderer.render(site_schema, selected.model_dump(), str(pdf_path))
        stage_log.append(_log("stage4", "PDF report generated."))

        serialiser = SchemaSerialiser()
        building_schema = serialiser.serialise(site_schema, selected.model_dump())
        stage_log.append(_log("stage4", "Building Schema serialised."))

    except Exception as exc:
        _logger.error("Job %s — Stage 4 failed: %s", job_id, exc)
        raise HTTPException(status_code=500, detail=f"Stage 4 rendering failed: {exc}") from exc

    # ------------------------------------------------------------------ fire-and-forget C02
    if _C02_ENDPOINT:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(_C02_ENDPOINT, json=building_schema)
                stage_log.append(_log("stage4", f"Building Schema sent to C02 — HTTP {resp.status_code}."))
        except Exception as exc:
            _logger.warning("Job %s — C02 POST failed (non-blocking): %s", job_id, exc)
            stage_log.append(_log("stage4", f"C02 POST skipped: {exc}"))
    else:
        stage_log.append(_log("stage4", "COMPONENT02_ENDPOINT not configured — C02 POST skipped."))

    # ------------------------------------------------------------------ Stage 5 (parallel)
    stage_log.append(_log("stage5", "Starting visualization generation."))

    try:
        import asyncio

        from stages.stage5_visualization.gemini_image_gen import generate_all_images
        from stages.stage5_visualization.gemini_text_gen import generate_all_text
        from stages.stage5_visualization.gemini_video_gen import generate_video

        images_task = generate_all_images(cadastral, zone, selected)
        text_task = generate_all_text(cadastral, zone, selected)

        images, (walkthrough_script, shopping_list) = await asyncio.gather(
            images_task, text_task
        )
        stage_log.append(_log("stage5", "Images, walkthrough script, and shopping list generated."))

        # Video always runs last (rate-limited)
        room_names = [r.name for r in selected.rooms]
        video_url, video_skipped_reason = await generate_video(
            district=cadastral.district,
            orientation=cadastral.orientation,
            room_names=room_names,
        )
        stage_log.append(_log("stage5", f"Video: {'generated' if video_url else video_skipped_reason}"))

    except Exception as exc:
        _logger.error("Job %s — Stage 5 failed: %s", job_id, exc)
        raise HTTPException(status_code=500, detail=f"Stage 5 visualization failed: {exc}") from exc

    # ------------------------------------------------------------------ Stage 6
    stage_log.append(_log("stage6", "Assembling final design package."))

    svg_url = f"/api/download/svg/{job_id}"
    pdf_url = f"/api/download/pdf/{job_id}"

    package = assemble(
        job_id=job_id,
        cadastral=cadastral,
        zone=zone,
        selected_plan=selected,
        svg_url=svg_url,
        pdf_url=pdf_url,
        building_schema=building_schema,
        images=images,
        walkthrough_script=walkthrough_script,
        shopping_list=shopping_list,
        video_url=video_url,
        video_skipped_reason=video_skipped_reason,
        stage_log=stage_log,
    )

    return package
