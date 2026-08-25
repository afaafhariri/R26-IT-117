"""Component 01 — AI-Based Architectural Planning API.

FastAPI application entry point for the 4-stage cadastral plan processing pipeline.
"""

import os

# Must be set before any paddle/paddleocr import to disable the PIR executor
# and OneDNN backend which are unsupported on Windows in PaddlePaddle 3.x.
os.environ.setdefault("FLAGS_enable_pir_api", "0")
os.environ.setdefault("FLAGS_use_mkldnn", "0")
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")  # force CPU

import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Load repo-root .env before any module reads os.getenv()
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from utils.logger import get_logger
from utils.file_handler import FileHandler

_logger = get_logger("main")

_ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/tiff",
}
_MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB

_file_handler = FileHandler()

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class SiteSchemaResponse(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    plan_id: str
    plan_number: Optional[str] = None
    district: str
    province: Optional[str] = None
    area_sqm: float
    scale: Optional[int] = None
    surveyor: Optional[str] = None
    lot_number: Optional[str] = None
    road_access: str
    is_coastal: bool
    orientation_degrees: float
    frontage_m: float
    boundary_polygon: list
    page_dimensions: dict
    coordinate_n: Optional[float] = None
    coordinate_e: Optional[float] = None
    gps_lat: Optional[float] = None
    gps_lon: Optional[float] = None
    licence_number: Optional[str] = None


class SetbackInputs(BaseModel):
    road_type: str = Field(..., description="national_road|provincial|local|lane")
    front_m: float = Field(..., gt=0)
    rear_m: float = Field(..., gt=0)
    side_m: float = Field(..., gt=0)
    coverage_ratio: float = Field(..., gt=0, le=1)
    floors_requested: int = Field(..., ge=1, le=5)


class BuildableZoneRequest(BaseModel):
    site_schema: dict
    setback_inputs: SetbackInputs


class BuildableZoneResponse(BaseModel):
    buildable_polygon: list
    max_footprint_sqm: float
    max_total_built_sqm: float
    recommended_floors: int
    setback_margins: dict
    coverage_achieved: float
    orientation: dict


class UserRequirements(BaseModel):
    room_types: list[str]
    room_count: int = Field(..., ge=1)
    garage: bool = False
    floors: int = Field(..., ge=1, le=5)
    budget_tier: str = Field(..., pattern="^(economy|medium|luxury)$")
    style: str = Field(default="modern", pattern="^(modern|traditional|contemporary)$")
    district: Optional[str] = None
    is_coastal: bool = False
    terrain: str = Field(
        default="flat",
        pattern="^(flat|sloped|hilly|rocky)$",
        description="Site terrain type — affects excavation cost in C02",
    )
    target_date: Optional[str] = Field(
        default=None,
        description="Expected construction start date ISO-8601 (YYYY-MM-DD) for C02 cost indexing",
    )


class FloorPlanRequest(BaseModel):
    buildable_zone: dict
    user_requirements: UserRequirements


class QualityScores(BaseModel):
    space_utilisation: float
    natural_light: float
    adjacency_quality: float
    ventilation_potential: float
    overall: float


class FloorPlanAlternative(BaseModel):
    layout_name: str
    layout_label: str
    temperature: float
    rooms: list[dict]
    total_area_sqm: float
    space_notes: str
    is_valid: bool
    violations: list[str]
    quality_scores: QualityScores


class RenderRequest(BaseModel):
    floor_plan: dict
    site_schema: dict
    buildable_zone: dict
    user_requirements: dict


class RenderResponse(BaseModel):
    svg_path: str
    pdf_path: str
    building_schema: dict
    download_urls: dict


class TaskStatusResponse(BaseModel):
    task_id: str
    status: str = Field(..., description="pending|processing|complete|failed")
    result: Optional[list] = None
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Lifespan (startup warm-up)
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    _logger.info("C01 Architectural Planning API starting up (version=0.1.0)")

    schema_dir = Path(os.getenv("SCHEMA_DIR", "shared/schemas"))
    if schema_dir.exists():
        for schema_file in schema_dir.glob("*.json"):
            try:
                _file_handler.load_schema(schema_file.name)
                _logger.info("Pre-loaded schema: %s", schema_file.name)
            except Exception as exc:
                _logger.warning("Could not pre-load schema %s: %s", schema_file.name, exc)
    else:
        _logger.warning("SCHEMA_DIR not found at %s — schemas will load on demand", schema_dir)

    yield

    _logger.info("C01 Architectural Planning API shutting down")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="C01 Architectural Planning API",
    version="0.1.0",
    description=(
        "Component 01 of Project R26-IT-117 — AI-Based Architectural Planning Model "
        "for Sri Lankan residential construction."
    ),
    lifespan=lifespan,
)

# CORS — allow the Vite dev server and any local origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routers
from routers import cadastral as _cadastral_router
from routers import design as _design_router
from routers import floorplans as _floorplans_router
from routers import video as _video_router

app.include_router(_cadastral_router.router, prefix="/api")
app.include_router(_floorplans_router.router, prefix="/api")
app.include_router(_design_router.router, prefix="/api")
app.include_router(_video_router.router, prefix="/api")


# ---------------------------------------------------------------------------
# POST /api/v1/extract
# ---------------------------------------------------------------------------

@app.post("/api/v1/extract", response_model=SiteSchemaResponse, tags=["Stage 1"])
async def extract(
    file: UploadFile = File(..., description="Cadastral plan PDF or image (max 50 MB)"),
    user_correction: bool = Query(default=False),
    plan_id: Optional[str] = Query(default=None),
    corrections: Optional[str] = Query(default=None, description="JSON string of field corrections"),
):
    """Runs the Stage 1 extraction pipeline on a cadastral plan upload.

    Accepts PDF, JPEG, PNG, or TIFF files up to 50 MB. Returns a validated
    Site Schema JSON conforming to site_schema.json.
    """
    if file.content_type not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Unsupported file type '{file.content_type}'. "
                f"Allowed: {sorted(_ALLOWED_CONTENT_TYPES)}"
            ),
        )

    raw = await file.read()
    if len(raw) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=422,
            detail=f"File exceeds 50 MB limit ({len(raw) / 1_048_576:.1f} MB uploaded)",
        )

    _logger.info(
        "File received: name=%s, type=%s, size=%d bytes",
        file.filename,
        file.content_type,
        len(raw),
    )

    suffix = Path(file.filename or "upload").suffix or ".bin"
    saved_path = _file_handler.save_upload(raw, file.filename or "upload", suffix)

    try:
        # Handle PDF → image conversion before OCR
        image_path = saved_path
        if file.content_type == "application/pdf":
            image_path = _pdf_to_image(saved_path)

        from stages.stage1_extraction.ocr_engine import OCREngine
        from stages.stage1_extraction.cnn_classifier import CadastralClassifier
        from stages.stage1_extraction.boundary_detector import BoundaryDetector
        from stages.stage1_extraction.ner_parser import NERParser
        from stages.stage1_extraction.schema_assembler import SchemaAssembler

        _logger.info("OCR started: %s", image_path)
        ocr_result = OCREngine().extract_text(image_path)
        _logger.info("OCR complete: %d tokens", len(ocr_result["tokens"]))

        classification = CadastralClassifier().classify(image_path)
        _logger.info(
            "CNN classification: type=%s, valid=%s",
            classification["plan_type"],
            classification["is_valid_cadastral"],
        )
        if not classification["is_valid_cadastral"]:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Uploaded file classified as '{classification['plan_type']}' "
                    "which is not a valid cadastral plan."
                ),
            )

        polygon = BoundaryDetector().detect_polygon(image_path)
        ner_result = NERParser().parse(ocr_result)

        # Apply user corrections if provided
        if user_correction and corrections:
            import json as _json
            try:
                correction_dict = _json.loads(corrections)
                ner_result.update(correction_dict)
                _logger.info("Applied user corrections: %s", list(correction_dict.keys()))
            except Exception as exc:
                _logger.warning("Could not apply corrections: %s", exc)

        site_schema = SchemaAssembler().assemble(ocr_result, polygon, ner_result)
        _logger.info("Schema assembled and validated: %s", site_schema["plan_id"])
        return SiteSchemaResponse(**site_schema)

    except HTTPException:
        raise
    except Exception as exc:
        _logger.error("Stage 1 pipeline error: %s", exc)
        raise HTTPException(status_code=500, detail=f"Stage 1 processing failed: {exc}")
    finally:
        _file_handler.cleanup(saved_path)
        if "image_path" in dir() and image_path != saved_path:
            _file_handler.cleanup(image_path)


def _pdf_to_image(pdf_path: Path) -> Path:
    """Converts the first page of a PDF to a PNG image for OCR processing."""
    import fitz

    doc = fitz.open(str(pdf_path))
    page = doc[0]
    mat = fitz.Matrix(2.0, 2.0)  # 2x zoom for better OCR resolution
    pix = page.get_pixmap(matrix=mat)
    out_path = pdf_path.with_suffix(".png")
    pix.save(str(out_path))
    doc.close()
    return out_path


# ---------------------------------------------------------------------------
# POST /api/v1/buildable-zone
# ---------------------------------------------------------------------------

@app.post("/api/v1/buildable-zone", response_model=BuildableZoneResponse, tags=["Stage 2"])
async def buildable_zone(request: BuildableZoneRequest):
    """Computes the buildable zone by applying NBC setbacks and BCR constraints.

    Returns the legal construction footprint polygon, max areas, and
    orientation recommendation.
    """
    try:
        from stages.stage2_buildable_zone.nbc_constraints import NBCConstraintEngine
        from stages.stage2_buildable_zone.polygon_calculator import BuildableZoneCalculator
        from stages.stage2_buildable_zone.orientation_solver import OrientationSolver

        nbc = NBCConstraintEngine()
        si = request.setback_inputs
        district = request.site_schema.get("district", "Colombo")
        is_coastal = request.site_schema.get("is_coastal", False)

        setbacks = {
            "front": si.front_m,
            "rear": si.rear_m,
            "side": si.side_m,
        }
        coverage_ratio = nbc.get_coverage_ratio(district, is_coastal)

        polygon = request.site_schema.get("boundary_polygon", [])
        real_area_sqm = float(request.site_schema.get("area_sqm") or 0)
        zone = BuildableZoneCalculator().calculate(
            polygon, setbacks, coverage_ratio, si.floors_requested, real_area_sqm
        )

        orientation = OrientationSolver().solve(
            zone["buildable_polygon"], request.site_schema
        )
        zone["orientation"] = orientation

        _logger.info(
            "Buildable zone computed: footprint=%.2f sqm", zone["max_footprint_sqm"]
        )
        return BuildableZoneResponse(**zone)

    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        _logger.error("Stage 2 pipeline error: %s", exc)
        raise HTTPException(status_code=500, detail=f"Stage 2 processing failed: {exc}")


# ---------------------------------------------------------------------------
# POST /api/v1/generate-floor-plan  (async via Celery)
# ---------------------------------------------------------------------------

@app.post("/api/v1/generate-floor-plan", tags=["Stage 3"])
async def generate_floor_plan(request: FloorPlanRequest):
    """Dispatches the Stage 3 floor plan generation pipeline as a Celery async task.

    Returns immediately with a task_id. Poll
    GET /api/v1/floor-plan-status/{task_id} for results.
    """
    try:
        from tasks.celery_app import generate_floor_plan_async

        task = generate_floor_plan_async.delay(
            request.buildable_zone,
            request.user_requirements.model_dump(),
        )
        _logger.info("Floor plan generation dispatched: task_id=%s", task.id)
        return {"task_id": task.id, "status": "processing"}

    except Exception as exc:
        _logger.error("Failed to dispatch generation task: %s", exc)
        raise HTTPException(
            status_code=500, detail=f"Failed to dispatch generation task: {exc}"
        )


# ---------------------------------------------------------------------------
# GET /api/v1/floor-plan-status/{task_id}
# ---------------------------------------------------------------------------

@app.get(
    "/api/v1/floor-plan-status/{task_id}",
    response_model=TaskStatusResponse,
    tags=["Stage 3"],
)
async def floor_plan_status(task_id: str):
    """Polls the Celery task result for a previously dispatched floor plan generation.

    Returns status: pending | processing | complete | failed, and the result
    list once complete.
    """
    try:
        from celery.result import AsyncResult
        from tasks.celery_app import celery_app

        result = AsyncResult(task_id, app=celery_app)

        if result.state == "PENDING":
            return TaskStatusResponse(task_id=task_id, status="pending")
        elif result.state == "STARTED":
            return TaskStatusResponse(task_id=task_id, status="processing")
        elif result.state == "SUCCESS":
            data = result.result or []
            if data and isinstance(data[0], dict) and "error" in data[0]:
                return TaskStatusResponse(
                    task_id=task_id,
                    status="failed",
                    error=data[0]["error"],
                )
            return TaskStatusResponse(
                task_id=task_id,
                status="complete",
                result=data,
            )
        else:
            return TaskStatusResponse(
                task_id=task_id,
                status="failed",
                error=str(result.result),
            )

    except Exception as exc:
        _logger.error("Task status poll failed: task_id=%s, error=%s", task_id, exc)
        raise HTTPException(status_code=500, detail=f"Status check failed: {exc}")


# ---------------------------------------------------------------------------
# POST /api/v1/render
# ---------------------------------------------------------------------------

@app.post("/api/v1/render", response_model=RenderResponse, tags=["Stage 4"])
async def render(request: RenderRequest):
    """Runs Stage 4: SVG render → PDF render → Building Schema serialisation.

    Validates the Building Schema against building_schema.json and attempts a
    fire-and-forget POST to Component 02.
    """
    try:
        from stages.stage4_renderer.svg_renderer import SVGRenderer
        from stages.stage4_renderer.pdf_renderer import PDFRenderer
        from stages.stage4_renderer.schema_serialiser import SchemaSerialiser

        import tempfile
        output_dir = Path(tempfile.gettempdir()) / "r26" / uuid.uuid4().hex
        output_dir.mkdir(parents=True, exist_ok=True)

        plan_id = request.site_schema.get("plan_id", "PLAN-UNKNOWN")
        svg_path = output_dir / f"{plan_id}.svg"
        pdf_path = output_dir / f"{plan_id}.pdf"

        _logger.info("Stage 4 rendering started for %s", plan_id)

        # Inject plan_id and budget_tier into floor_plan for SVG title block
        floor_plan_enriched = {
            **request.floor_plan,
            "plan_id": plan_id,
            "budget_tier": request.user_requirements.get("budget_tier", "medium"),
        }

        svg_out = SVGRenderer().render(
            floor_plan_enriched, request.buildable_zone, svg_path
        )

        quality_scores = floor_plan_enriched.get("quality_scores", {})
        pdf_out = PDFRenderer().render(
            svg_out,
            request.site_schema,
            request.buildable_zone,
            floor_plan_enriched,
            quality_scores,
            pdf_path,
        )

        building_schema = SchemaSerialiser().serialise(
            floor_plan_enriched,
            request.site_schema,
            request.buildable_zone,
            request.user_requirements,
        )

        _logger.info("Stage 4 rendering complete for %s", plan_id)

        return RenderResponse(
            svg_path=str(svg_out),
            pdf_path=str(pdf_out),
            building_schema=building_schema,
            download_urls={
                "svg": f"/api/v1/download/{svg_out.name}?dir={output_dir.name}",
                "pdf": f"/api/v1/download/{pdf_out.name}?dir={output_dir.name}",
            },
        )

    except Exception as exc:
        _logger.error("Stage 4 pipeline error: %s", exc)
        raise HTTPException(status_code=500, detail=f"Stage 4 rendering failed: {exc}")


# ---------------------------------------------------------------------------
# GET /api/v1/download/{filename}
# ---------------------------------------------------------------------------

@app.get("/api/v1/download/{filename}", tags=["Stage 4"])
async def download(filename: str, dir: str = Query(...)):
    """Downloads a rendered SVG or PDF file by filename and temp directory name."""
    import tempfile
    file_path = Path(tempfile.gettempdir()) / "r26" / dir / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {filename}")
    media_type = "image/svg+xml" if filename.endswith(".svg") else "application/pdf"
    return FileResponse(str(file_path), media_type=media_type, filename=filename)


# ---------------------------------------------------------------------------
# GET /api/v1/health
# ---------------------------------------------------------------------------

@app.get("/api/v1/health", tags=["System"])
async def health():
    """Returns API health status."""
    return {"status": "ok", "component": "C01", "version": "0.1.0"}
