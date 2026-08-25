"""GET /api/download/svg/{job_id} and /api/download/pdf/{job_id}"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from utils.logger import get_logger

_logger = get_logger("router.downloads")

router = APIRouter()

_TEMP_DIR = Path(os.getenv("TEMP_FILES_DIR", "./tmp"))


@router.get("/download/svg/{job_id}")
async def download_svg(job_id: str):
    path = _TEMP_DIR / f"{job_id}_floor_plan.svg"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"SVG not found for job {job_id}.")
    _logger.info("Serving SVG for job %s", job_id)
    return FileResponse(
        path=str(path),
        media_type="image/svg+xml",
        filename=f"floor_plan_{job_id}.svg",
    )


@router.get("/download/pdf/{job_id}")
async def download_pdf(job_id: str):
    path = _TEMP_DIR / f"{job_id}_report.pdf"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"PDF not found for job {job_id}.")
    _logger.info("Serving PDF for job %s", job_id)
    return FileResponse(
        path=str(path),
        media_type="application/pdf",
        filename=f"report_{job_id}.pdf",
    )
