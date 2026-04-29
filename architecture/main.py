"""
main.py — FastAPI entry point for Component 01: AI-Driven Construction Planner.

Pipeline:
  POST /extract           -> Site Schema JSON
  POST /buildable-zone    -> Buildable Zone JSON
  POST /generate-floor-plan -> 3 x Floor Plan JSON options
  POST /render            -> SVG + PDF + Building Schema JSON
"""

import os
import uuid
import logging
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, UploadFile, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from stages.stage1_extraction.ocr_engine import OCREngine
from stages.stage1_extraction.boundary_detector import BoundaryDetector
from stages.stage1_extraction.ner_parser import NERParser
from stages.stage1_extraction.schema_assembler import SchemaAssembler

from stages.stage2_buildable_zone.nbc_constraints import NBCConstraintEngine
from stages.stage2_buildable_zone.polygon_calculator import BuildableZoneCalculator
from stages.stage2_buildable_zone.orientation_solver import OrientationSolver

from stages.stage3_floor_plan.rag_retriever import RAGRetriever
from stages.stage3_floor_plan.prompt_builder import PromptBuilder
from stages.stage3_floor_plan.llm_generator import FloorPlanGenerator
from stages.stage3_floor_plan.validator import LayoutValidator
from stages.stage3_floor_plan.scorer import LayoutScorer

from stages.stage4_renderer.svg_renderer import SVGRenderer
from stages.stage4_renderer.pdf_renderer import PDFRenderer
from stages.stage4_renderer.schema_serialiser import SchemaSerialiser

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "/tmp/uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title="AI-Driven Construction Planner — Component 01",
    description="4-stage pipeline: extract → buildable zone → floor plan → render",
    version="1.0.0",
)


# ---------------------------------------------------------------------------
# Pydantic request / response models
# ---------------------------------------------------------------------------

class BuildableZoneRequest(BaseModel):
    site_schema: dict = Field(..., description="Site Schema JSON from /extract")
    road_type: str = Field(
        "local",
        description="Road type: national_road | provincial | local | lane",
    )


class FloorPlanRequest(BaseModel):
    buildable_zone: dict = Field(..., description="Buildable Zone JSON from /buildable-zone")
    user_requirements: dict = Field(
        ...,
        description=(
            "User requirements: rooms list, finish_grade, style, "
            "num_floors, special_requirements"
        ),
    )


class RenderRequest(BaseModel):
    approved_floor_plan: dict = Field(
        ..., description="One approved floor plan JSON from /generate-floor-plan"
    )
    site_schema: dict = Field(..., description="Site Schema JSON from /extract")
    buildable_zone: dict = Field(..., description="Buildable Zone JSON from /buildable-zone")


# ---------------------------------------------------------------------------
# Stage 1 — /extract
# ---------------------------------------------------------------------------

@app.post("/extract", summary="Extract site schema from cadastral plan PDF/image")
async def extract(file: UploadFile = File(...)) -> JSONResponse:
    """
    Accept a Sri Lankan cadastral survey plan (PDF or image).
    Runs OCR, boundary detection, NER, and assembles a validated Site Schema JSON.
    """
    suffix = Path(file.filename).suffix.lower()
    if suffix not in {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif"}:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type: {suffix}",
        )

    tmp_path = UPLOAD_DIR / f"{uuid.uuid4()}{suffix}"
    try:
        content = await file.read()
        tmp_path.write_bytes(content)

        ocr_engine = OCREngine()
        boundary_detector = BoundaryDetector()
        ner_parser = NERParser()
        assembler = SchemaAssembler()

        ocr_result = ocr_engine.extract_text(tmp_path)
        polygon = boundary_detector.detect_polygon(tmp_path)
        ner_result = ner_parser.parse(ocr_result)
        site_schema = assembler.assemble(ocr_result, polygon, ner_result)

        return JSONResponse(content=site_schema, status_code=status.HTTP_200_OK)

    except ValueError as exc:
        logger.error("Extraction validation error: %s", exc)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except Exception as exc:
        logger.exception("Extraction failed")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


# ---------------------------------------------------------------------------
# Stage 2 — /buildable-zone
# ---------------------------------------------------------------------------

@app.post("/buildable-zone", summary="Calculate buildable zone from site schema")
async def buildable_zone(request: BuildableZoneRequest) -> JSONResponse:
    """
    Apply NBC (National Building Code) setbacks and coverage rules to derive
    the buildable footprint polygon and recommended floor count.
    """
    try:
        nbc = NBCConstraintEngine()
        calculator = BuildableZoneCalculator()
        solver = OrientationSolver()

        setbacks = nbc.get_setbacks(request.road_type)
        coverage_ratio = nbc.get_coverage_ratio(
            request.site_schema.get("site", {}).get("district", "default")
        )

        boundary_polygon = request.site_schema["boundaries"]["polygon"]
        zone = calculator.calculate(boundary_polygon, setbacks, coverage_ratio)

        orientation_degrees = request.site_schema["boundaries"].get("orientation_degrees", 0.0)
        zone["optimal_orientation"] = solver.solve(orientation_degrees)

        return JSONResponse(content=zone, status_code=status.HTTP_200_OK)

    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Missing field in site_schema: {exc}",
        )
    except Exception as exc:
        logger.exception("Buildable zone calculation failed")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


# ---------------------------------------------------------------------------
# Stage 3 — /generate-floor-plan
# ---------------------------------------------------------------------------

@app.post("/generate-floor-plan", summary="Generate 3 floor plan options via LLM")
async def generate_floor_plan(request: FloorPlanRequest) -> JSONResponse:
    """
    Use RAG-augmented LLM calls at three temperature settings to produce
    3 validated and scored floor plan JSON alternatives.
    """
    try:
        retriever = RAGRetriever()
        prompt_builder = PromptBuilder()
        generator = FloorPlanGenerator()
        validator = LayoutValidator()
        scorer = LayoutScorer()

        retrieved = retriever.retrieve(request.buildable_zone, request.user_requirements)
        prompt = prompt_builder.build(request.buildable_zone, request.user_requirements, retrieved)
        plans = generator.generate(prompt)

        results: list[dict[str, Any]] = []
        for plan in plans:
            is_valid, violations = validator.validate(plan, request.buildable_zone)
            scores = scorer.score(plan)
            results.append(
                {
                    "floor_plan": plan,
                    "is_valid": is_valid,
                    "violations": violations,
                    "scores": scores,
                }
            )

        return JSONResponse(content={"options": results}, status_code=status.HTTP_200_OK)

    except Exception as exc:
        logger.exception("Floor plan generation failed")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


# ---------------------------------------------------------------------------
# Stage 4 — /render
# ---------------------------------------------------------------------------

@app.post("/render", summary="Render approved floor plan to SVG, PDF, and Building Schema JSON")
async def render(request: RenderRequest) -> JSONResponse:
    """
    Accept an approved floor plan and produce:
      - SVG floor plan drawing (base64-encoded)
      - PDF floor plan drawing (base64-encoded)
      - Building Schema JSON (feeds Component 02)
    """
    try:
        svg_renderer = SVGRenderer()
        pdf_renderer = PDFRenderer()
        serialiser = SchemaSerialiser()

        svg_b64 = svg_renderer.render(request.approved_floor_plan)
        pdf_b64 = pdf_renderer.render(request.approved_floor_plan)
        building_schema = serialiser.serialise(
            request.approved_floor_plan,
            request.site_schema,
            request.buildable_zone,
        )

        return JSONResponse(
            content={
                "svg_b64": svg_b64,
                "pdf_b64": pdf_b64,
                "building_schema": building_schema,
            },
            status_code=status.HTTP_200_OK,
        )

    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except Exception as exc:
        logger.exception("Rendering failed")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health", summary="Health check")
async def health() -> dict[str, str]:
    return {"status": "ok", "component": "01"}
