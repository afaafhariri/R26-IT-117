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


def _suggest_requirements(area_sqm: float) -> dict:
    """Suggest rooms and floors based on total land area."""
    if area_sqm < 80:
        bedrooms, bathrooms, floors, garage = 2, 1, 1, False
    elif area_sqm < 150:
        bedrooms, bathrooms, floors, garage = 3, 2, 1, False
    elif area_sqm < 250:
        bedrooms, bathrooms, floors, garage = 3, 2, 2, False
    elif area_sqm < 400:
        bedrooms, bathrooms, floors, garage = 4, 2, 2, True
    else:
        bedrooms, bathrooms, floors, garage = 4, 3, 2, True

    return {
        "bedrooms": bedrooms,
        "bathrooms": bathrooms,
        "living_room": True,
        "kitchen": True,
        "dining_room": True,
        "garage": garage,
        "floors": floors,
        "style": "modern",
    }


def compute_buildable_zone(
    boundary_polygon: list,
    area_sqm: float,
    district: str,
    is_coastal: bool,
    road_type: str,
    floors: int,
) -> dict:
    """Regulation-aware buildable zone, as BuildableZone fields.

    Applies the road-type setbacks and the building coverage ratio (BCR) from
    NBCConstraintEngine through BuildableZoneCalculator. When the coverage
    limit is the binding constraint, the setback polygon is shrunk about its
    centroid until its real area equals the permitted footprint, so the zone
    outline that Stage 3 packs rooms into matches the area it is allowed to
    cover (packing into the larger setback outline would let the layout
    exceed the coverage limit).

    Raises:
        ValueError: invalid polygon or a plot below the 50 sqm minimum.
    """
    from shapely.affinity import scale as _scale
    from shapely.geometry import Polygon as _Polygon

    from stages.stage2_buildable_zone.nbc_constraints import NBCConstraintEngine
    from stages.stage2_buildable_zone.polygon_calculator import BuildableZoneCalculator

    nbc = NBCConstraintEngine()
    setbacks = nbc.get_setbacks(road_type)
    bcr = nbc.get_coverage_ratio(district, is_coastal)
    result = BuildableZoneCalculator().calculate(boundary_polygon, setbacks, bcr, floors, area_sqm)

    footprint = float(result["max_footprint_sqm"])
    polygon = result["buildable_polygon"]
    site_norm_area = _Polygon(boundary_polygon).area
    zone_poly = _Polygon(polygon)
    offset_sqm = zone_poly.area * (area_sqm / site_norm_area) if site_norm_area > 0 else 0.0
    if 0 < footprint < offset_sqm:
        factor = (footprint / offset_sqm) ** 0.5
        zone_poly = _scale(zone_poly, xfact=factor, yfact=factor, origin="centroid")
        polygon = [[x, y] for x, y in zone_poly.exterior.coords]

    total = footprint * floors
    min_setback = min(setbacks.values())
    return {
        "buildable_polygon": [(float(x), float(y)) for x, y in polygon],
        "buildable_area_sqft": _sqm_to_sqft(footprint),
        "buildable_area_sqm": round(footprint, 2),
        "max_footprint_sqm": round(footprint, 2),
        "max_total_built_sqm": round(total, 2),
        "max_floors": floors,
        "bcr_value": bcr,
        "front_setback_ft": _m_to_ft(setbacks["front"]),
        "rear_setback_ft": _m_to_ft(setbacks["rear"]),
        "side_setbacks_ft": [_m_to_ft(setbacks["side"]), _m_to_ft(setbacks["side"])],
        "constraints_summary": (
            f"{road_type.replace('_', ' ').title()} access: setbacks front {setbacks['front']} m, "
            f"rear {setbacks['rear']} m, side {setbacks['side']} m (applied as a uniform "
            f"{min_setback} m inset); coverage limit {bcr:.0%} of {area_sqm:.1f} sqm. "
            f"Footprint {footprint:.1f} sqm x {floors} floor(s) = {total:.1f} sqm total buildable."
        ),
    }


def _fit_suggestion(suggested: dict, total_built_sqm: float) -> dict:
    """Trims the suggested programme until its minimum room areas fit the
    buildable total, so a regulated footprint never starts the user on a
    brief that cannot be built. Drops, in order: garage, dining room, extra
    bathrooms, extra bedrooms (never below one bedroom and one bathroom)."""
    from stages.stage3_floor_plan.prompt_builder import _MIN_ROOM_SQM

    s = dict(suggested)

    def need(x: dict) -> float:
        beds = max(x["bedrooms"], 1)
        total = _MIN_ROOM_SQM["master_bedroom"] + (beds - 1) * _MIN_ROOM_SQM["bedroom"]
        total += x["bathrooms"] * _MIN_ROOM_SQM["bathroom"]
        total += _MIN_ROOM_SQM["living_room"] + _MIN_ROOM_SQM["kitchen"]
        total += _MIN_ROOM_SQM["dining_room"] if x["dining_room"] else 0.0
        total += _MIN_ROOM_SQM["garage"] if x["garage"] else 0.0
        return total

    while need(s) > total_built_sqm:
        if s["garage"]:
            s["garage"] = False
        elif s["dining_room"]:
            s["dining_room"] = False
        elif s["bathrooms"] > 1:
            s["bathrooms"] -= 1
        elif s["bedrooms"] > 1:
            s["bedrooms"] -= 1
        else:
            break
    return s


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
        from stages.stage1_extraction.cnn_classifier import CadastralClassifier as CNNClassifier
        from stages.stage1_extraction.ner_parser import NERParser
        from stages.stage1_extraction.ocr_engine import OCREngine
        from stages.stage1_extraction.schema_assembler import SchemaAssembler
        from stages.stage2_buildable_zone.nbc_constraints import NBCConstraintEngine
        from stages.stage2_buildable_zone.orientation_solver import OrientationSolver
        from stages.stage2_buildable_zone.polygon_calculator import BuildableZoneCalculator as PolygonCalculator

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
        boundary_polygon = bd.detect_polygon(img_path)
        boundary = {"polygon": boundary_polygon}

        assembler = SchemaAssembler()
        site_schema = assembler.assemble(text_tokens, boundary_polygon, entities)

        # ---- Stage 2 — regulation-aware buildable envelope ----
        # Road-type setbacks and the building coverage ratio (BCR) come from
        # NBCConstraintEngine, the same way /api/v1/buildable-zone applies them.
        area_sqm = site_schema.get("area_sqm") or 0.0
        district = site_schema.get("district") or "Unknown"
        road_type = site_schema.get("road_access") or "local"   # national_road | provincial | local | lane
        is_coastal = bool(site_schema.get("is_coastal"))
        # Display vocabulary of CadastralData ("main road" | "lane" | "private road")
        road = "main road" if road_type in ("national_road", "provincial") else "lane"

        suggested = _suggest_requirements(area_sqm)
        max_floors = suggested["floors"]

        try:
            zone_fields = compute_buildable_zone(
                boundary_polygon, area_sqm, district, is_coastal, road_type, max_floors
            )
        except ValueError as exc:
            # Unreadable extent, too few boundary vertices, or a plot below the
            # 50 sqm minimum: tell the user what is wrong instead of a 500.
            raise HTTPException(
                status_code=422,
                detail=f"Could not compute a buildable zone from this plan: {exc}",
            ) from exc

        suggested = _fit_suggestion(suggested, zone_fields["max_total_built_sqm"])
        zone_result = {"buildable_polygon": zone_fields["buildable_polygon"]}

        orientation_solver = OrientationSolver()
        orientation_result = orientation_solver.solve(zone_result["buildable_polygon"], site_schema)
        # orientation_result has no "cardinal" key — solve() returns entrance_side.
        # (Reading a key it never produces meant this always fell through to the
        # hardcoded default below, regardless of the plot's actual orientation.)
        entrance_side = (
            orientation_result.get("entrance_side", "north")
            if isinstance(orientation_result, dict) else "north"
        )
        orientation_str = f"{entrance_side.capitalize()}-facing"

        plot_poly = [(float(pt[0]), float(pt[1])) for pt in boundary_polygon]
        build_poly = [
            (float(pt[0]), float(pt[1]))
            for pt in zone_result.get("buildable_polygon", boundary_polygon)
        ]

        gps_lat = site_schema.get("gps_lat")
        gps_lon = site_schema.get("gps_lon")
        coord_n = site_schema.get("coordinate_n")
        coord_e = site_schema.get("coordinate_e")

        cadastral = CadastralData(
            land_area_perches=_sqm_to_perches(area_sqm),
            land_area_sqft=_sqm_to_sqft(area_sqm),
            district=district,
            road_access_type=road,
            gps_coordinates=[(gps_lat, gps_lon)] if gps_lat and gps_lon else [],
            sld99_coordinates=[(coord_n, coord_e)] if coord_n and coord_e else [],
            plot_boundary_polygon=plot_poly,
            orientation=orientation_str,
            raw_ocr_text=text_tokens.get("raw_text", "")[:2000],
            extracted_entities=entities,
        )

        zone = BuildableZone(**{**zone_fields, "buildable_polygon": build_poly})

        # ---- persist in Redis for downstream stages ----
        r = _get_redis()
        r.setex(f"job:{job_id}:cadastral", _JOB_TTL, cadastral.model_dump_json())
        r.setex(f"job:{job_id}:zone", _JOB_TTL, zone.model_dump_json())
        r.setex(f"job:{job_id}:site_schema", _JOB_TTL, json.dumps(site_schema))
        r.setex(f"job:{job_id}:suggested_requirements", _JOB_TTL, json.dumps(suggested))

        _logger.info("Job %s — Stage 1+2 complete: district=%s area_sqm=%.1f suggested=%s",
                     job_id, cadastral.district, area_sqm, suggested)

        return {
            "job_id": job_id,
            "cadastral_data": cadastral,
            "buildable_zone": zone,
            "suggested_requirements": suggested,
        }

    except HTTPException:
        raise
    except Exception as exc:
        _logger.error("Job %s — pipeline error: %s", job_id, exc)
        raise HTTPException(status_code=500, detail=f"Processing failed: {exc}") from exc
    finally:
        # clean up upload file; keep img for downstream if PDF was converted
        if upload_path.exists():
            upload_path.unlink(missing_ok=True)
