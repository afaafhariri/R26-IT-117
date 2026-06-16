"""POST /api/process-cadastral — Stage 1 + Stage 2 pipeline."""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

import redis
from fastapi import APIRouter, HTTPException, UploadFile

from models.schemas import BuildableZone, CadastralData
from utils.logger import get_logger

_logger = get_logger("router.cadastral")

router = APIRouter()

_TEMP_DIR = Path(os.getenv("TEMP_FILES_DIR", "./tmp"))
_REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
_JOB_TTL = 7200   # 2 hours


def _get_redis() -> redis.Redis:
    return redis.from_url(_REDIS_URL, decode_responses=True)


def _sqm_to_sqft(sqm: float) -> float:
    return round(sqm * 10.7639, 2)


def _sqm_to_perches(sqm: float) -> float:
    return round(sqm / 25.2929, 2)


def _m_to_ft(m: float) -> float:
    return round(m * 3.28084, 2)


@router.post("/process-cadastral")
async def process_cadastral(file: UploadFile):
    """Accept a cadastral plan PDF/image, run Stage 1 + Stage 2, return structured data."""

    # ---- validate upload ----
    max_mb = int(os.getenv("MAX_UPLOAD_SIZE_MB", "20"))
    contents = await file.read()
    if len(contents) > max_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"File exceeds {max_mb}MB limit.")

    suffix = Path(file.filename or "upload").suffix.lower()
    if suffix not in {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif"}:
        raise HTTPException(status_code=400, detail="Unsupported file type.")

    job_id = str(uuid.uuid4())
    _TEMP_DIR.mkdir(parents=True, exist_ok=True)
    upload_path = _TEMP_DIR / f"{job_id}_upload{suffix}"
    upload_path.write_bytes(contents)

    _logger.info("Job %s — file saved: %s (%d bytes)", job_id, upload_path.name, len(contents))

    try:
        # ---- lazy imports (heavy ML — keep startup fast) ----
        from pathlib import Path as _Path

        import fitz  # PyMuPDF

        from stages.stage1_extraction.boundary_detector import BoundaryDetector
        from stages.stage1_extraction.cnn_classifier import CNNClassifier
        from stages.stage1_extraction.ner_parser import NERParser
        from stages.stage1_extraction.ocr_engine import OCREngine
        from stages.stage1_extraction.schema_assembler import SchemaAssembler
        from stages.stage2_buildable_zone.nbc_constraints import NBCConstraintEngine
        from stages.stage2_buildable_zone.orientation_solver import OrientationSolver
        from stages.stage2_buildable_zone.polygon_calculator import PolygonCalculator

        # ---- convert PDF to image if needed ----
        if suffix == ".pdf":
            doc = fitz.open(str(upload_path))
            page = doc[0]
            pix = page.get_pixmap(dpi=200)
            img_path = _TEMP_DIR / f"{job_id}_page.png"
            pix.save(str(img_path))
            doc.close()
        else:
            img_path = upload_path

        # ---- Stage 1 ----
        cnn = CNNClassifier()
        cls_result = cnn.classify(img_path)
        if not cls_result.get("is_valid_cadastral", True):
            raise HTTPException(status_code=400, detail="Uploaded file is not a valid cadastral plan.")

        ocr = OCREngine()
        text_tokens = ocr.extract_text(img_path)

        ner = NERParser()
        entities = ner.parse(text_tokens)

        bd = BoundaryDetector()
        boundary = bd.detect(img_path)

        assembler = SchemaAssembler()
        site_schema = assembler.assemble(entities, boundary, text_tokens)

        # ---- Stage 2 ----
        nbc = NBCConstraintEngine()
        constraints = nbc.compute(site_schema)

        calc = PolygonCalculator()
        zone_polygon = calc.compute_buildable_polygon(
            boundary["polygon"], constraints
        )

        orientation_solver = OrientationSolver()
        orientation = orientation_solver.solve(
            site_schema.get("gps_lat"), site_schema.get("gps_lon"), constraints
        )

        # ---- map to Pydantic schemas ----
        area_sqm = site_schema.get("area_sqm") or 0.0
        buildable_sqm = constraints.get("buildable_area_sqm", area_sqm * 0.5)

        plot_poly = [
            (float(pt[0]), float(pt[1])) for pt in (boundary.get("polygon") or [])
        ]
        build_poly = [
            (float(pt[0]), float(pt[1])) for pt in (zone_polygon or plot_poly)
        ]

        gps_lat = site_schema.get("gps_lat")
        gps_lon = site_schema.get("gps_lon")
        coord_n = site_schema.get("coordinate_n")
        coord_e = site_schema.get("coordinate_e")

        road = (site_schema.get("road_access") or "lane").lower()
        if road not in ("main road", "lane", "private road"):
            road = "lane"

        cadastral = CadastralData(
            land_area_perches=_sqm_to_perches(area_sqm),
            land_area_sqft=_sqm_to_sqft(area_sqm),
            district=site_schema.get("district") or "Unknown",
            road_access_type=road,
            gps_coordinates=[(gps_lat, gps_lon)] if gps_lat and gps_lon else [],
            sld99_coordinates=[(coord_n, coord_e)] if coord_n and coord_e else [],
            plot_boundary_polygon=plot_poly,
            orientation=orientation or "North-facing",
            raw_ocr_text=text_tokens.get("raw_text", "")[:2000],
            extracted_entities=entities,
        )

        front_m = constraints.get("front_setback_m", 1.0)
        rear_m = constraints.get("rear_setback_m", 1.5)
        side_m = constraints.get("side_setback_m", 1.0)

        zone = BuildableZone(
            buildable_polygon=build_poly,
            buildable_area_sqft=_sqm_to_sqft(buildable_sqm),
            bcr_value=constraints.get("bcr", 0.5),
            front_setback_ft=_m_to_ft(front_m),
            rear_setback_ft=_m_to_ft(rear_m),
            side_setbacks_ft=[_m_to_ft(side_m), _m_to_ft(side_m)],
            constraints_summary=constraints.get("summary", "NBC Sri Lanka rules applied."),
        )

        # ---- persist in Redis for downstream stages ----
        r = _get_redis()
        r.setex(f"job:{job_id}:cadastral", _JOB_TTL, cadastral.model_dump_json())
        r.setex(f"job:{job_id}:zone", _JOB_TTL, zone.model_dump_json())
        r.setex(f"job:{job_id}:site_schema", _JOB_TTL, json.dumps(site_schema))

        _logger.info("Job %s — Stage 1+2 complete: district=%s area_sqm=%.1f",
                     job_id, cadastral.district, area_sqm)

        return {"job_id": job_id, "cadastral_data": cadastral, "buildable_zone": zone}

    except HTTPException:
        raise
    except Exception as exc:
        _logger.error("Job %s — pipeline error: %s", job_id, exc)
        raise HTTPException(status_code=500, detail=f"Processing failed: {exc}") from exc
    finally:
        # clean up upload file; keep img for downstream if PDF was converted
        if upload_path.exists():
            upload_path.unlink(missing_ok=True)
