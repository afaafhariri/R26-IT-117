"""
Component 04 — Timeline Generation Service.

FastAPI application that exposes four endpoints:

  POST /timeline/generate          — run the full pipeline, return timeline JSON
  GET  /timeline/{project_id}      — fetch a saved timeline from PostgreSQL
  POST /timeline/{project_id}/update — record actual phase completion data
  GET  /timeline/{project_id}/gantt  — return only the Gantt chart data

All credentials are read from environment variables — never hardcoded.
"""

import logging
import os
from datetime import date
from typing import Any

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field

from timeline.output.gantt_builder import GanttBuilder
from timeline.output.timeline_serialiser import TimelineSerialiser
from timeline.pipeline.critical_path import CriticalPathEngine
from timeline.pipeline.feature_engineer import FeatureEngineer
from timeline.pipeline.preprocessor import Preprocessor
from timeline.pipeline.schedule_model import ScheduleModel

logger = logging.getLogger(__name__)

app = FastAPI(
    title="AI-Driven Construction Planner — Timeline Service",
    description="Component 04: generates a construction timeline with critical path and Gantt data.",
    version="1.0.0",
)

# ── Singleton pipeline objects (loaded once at startup) ───────────────────────

_preprocessor    = Preprocessor()
_feature_engineer = FeatureEngineer()
_schedule_model  = ScheduleModel()
_cp_engine       = CriticalPathEngine()
_gantt_builder   = GanttBuilder()
_serialiser      = TimelineSerialiser()


@app.on_event("startup")
async def _startup() -> None:
    """Load trained XGBoost models if they exist; otherwise stub rules are used."""
    model_dir = os.getenv("MODEL_DIR", "models")
    _schedule_model.load_models(model_dir)
    logger.info("Timeline service started. Model dir: %s", model_dir)


# ── Request / Response models (Pydantic v2) ───────────────────────────────────

class GenerateTimelineRequest(BaseModel):
    """Payload for POST /timeline/generate."""

    building_schema: dict[str, Any] = Field(
        ...,
        description="Building Schema JSON from Component 01 (Architecture).",
    )
    cost_report: dict[str, Any] = Field(
        ...,
        description="Cost Report JSON from Component 02 (Cost Estimation).",
    )
    project_start_date: date | None = Field(
        default=None,
        description="Desired project start date (ISO 8601). Defaults to today.",
    )

    model_config = {"json_schema_extra": {
        "example": {
            "building_schema": {
                "project_id": "proj-001",
                "floors": 2,
                "footprint_sqm": 150.0,
                "total_area_sqm": 300.0,
                "finish_grade": "standard",
                "roof_type": "pitched",
                "foundation_type": "strip",
                "location_coastal": False,
                "district": "Colombo",
            },
            "cost_report": {
                "total_labour_days": 400,
                "structural_complexity_score": 1.2,
                "total_cost": 18000000.0,
                "trade_value_breakdown": {
                    "civil": 8000000.0,
                    "mep": 4000000.0,
                    "finishing": 6000000.0,
                },
            },
            "project_start_date": "2025-06-01",
        }
    }}


class PhaseUpdateEntry(BaseModel):
    """Single phase completion record for POST /timeline/{project_id}/update."""

    phase: str = Field(..., description="Phase name matching ALL_PHASES constants.")
    actual_duration_days: int = Field(..., ge=1)
    completion_date: date


class TimelineUpdateRequest(BaseModel):
    """Payload for POST /timeline/{project_id}/update."""

    completed_phases: list[PhaseUpdateEntry]


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.post(
    "/timeline/generate",
    status_code=status.HTTP_200_OK,
    summary="Generate a full construction timeline",
)
async def generate_timeline(req: GenerateTimelineRequest) -> dict:
    """
    Run the five-stage pipeline and return a Timeline JSON document.

    Pipeline stages:
    1. Preprocessor     — extract and encode raw fields
    2. FeatureEngineer  — derive analytical features
    3. ScheduleModel    — predict phase durations
    4. CriticalPathEngine — CPM forward/backward pass
    5. GanttBuilder + TimelineSerialiser — produce output document
    """
    try:
        start_date = req.project_start_date or date.today()

        df_pre      = _preprocessor.prepare(req.building_schema, req.cost_report)
        df_features = _feature_engineer.build_features(df_pre)

        phase_durations = _schedule_model.predict_phase_durations(df_features)
        graph           = _cp_engine.build_network(phase_durations)
        cp_result       = _cp_engine.calculate(graph)

        gantt    = _gantt_builder.build(phase_durations, cp_result, start_date)
        timeline = _serialiser.serialise(
            phase_durations,
            cp_result,
            gantt,
            req.building_schema,
            req.cost_report,
        )

        # TODO: persist timeline to PostgreSQL
        #   db_session.add(TimelineRecord(**timeline))
        #   db_session.commit()

        return timeline

    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Unexpected error in generate_timeline")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error") from exc


@app.get(
    "/timeline/{project_id}",
    status_code=status.HTTP_200_OK,
    summary="Retrieve a saved timeline",
)
async def get_timeline(project_id: str) -> dict:
    """
    Fetch the most recent timeline document for the given project_id
    from PostgreSQL.
    """
    # TODO: query PostgreSQL
    #   record = db_session.query(TimelineRecord).filter_by(project_id=project_id).first()
    #   if not record:
    #       raise HTTPException(status_code=404, detail="Timeline not found")
    #   return record.data
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=f"Database retrieval for project '{project_id}' is not yet implemented.",
    )


@app.post(
    "/timeline/{project_id}/update",
    status_code=status.HTTP_200_OK,
    summary="Update timeline with actual phase completion data",
)
async def update_timeline(project_id: str, req: TimelineUpdateRequest) -> dict:
    """
    Record actual phase durations to enable schedule variance analysis in
    Component 05 (Performance Monitoring).

    Recalculates the remaining critical path for phases not yet completed.
    """
    # TODO: load existing timeline from PostgreSQL
    # TODO: apply actual durations, recalculate remaining CPM
    # TODO: persist updated record
    return {
        "project_id": project_id,
        "updated_phases": [e.phase for e in req.completed_phases],
        "message": "Update received — database write not yet implemented.",
    }


@app.get(
    "/timeline/{project_id}/gantt",
    status_code=status.HTTP_200_OK,
    summary="Return Gantt chart data for a project",
)
async def get_gantt(project_id: str) -> dict:
    """
    Return the Gantt chart data structure (phases list) for the given project.
    Suitable for direct consumption by a front-end Gantt library.
    """
    # TODO: fetch from PostgreSQL and return timeline["phases"]
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=f"Gantt retrieval for project '{project_id}' is not yet implemented.",
    )


# ── Dev entry-point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8004")),
        reload=os.getenv("RELOAD", "false").lower() == "true",
    )
