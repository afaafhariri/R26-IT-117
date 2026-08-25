"""
Component 04 - Timeline Generation Service.

Endpoints
---------
  POST /predict   - accepts building details, returns phase predictions +
                    critical path + Gantt task list
  POST /progress  - accepts actual phase durations, returns deviation
                    analysis and alert level
  GET  /health    - liveness / readiness check
"""

from __future__ import annotations

import logging
import os
from datetime import date
from typing import Any

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

from models import load_model
from pipeline import (
    Preprocessor,
    FeatureEngineer,
    CriticalPathEngine,
    ALL_PHASES,
)
from pipeline.lstm_predictor import LSTMPredictor

# -- Logging ------------------------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# -- App ----------------------------------------------------------------------
app = FastAPI(
    title="AI-Driven Construction Planner - Timeline Service",
    description="Component 04: predicts construction phase durations for Sri Lankan residential buildings, computes the critical path, and returns a Gantt-ready task list.",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -- Singleton pipeline objects -----------------------------------------------
_preprocessor     = Preprocessor()
_feature_engineer = FeatureEngineer()
_cp_engine        = CriticalPathEngine()
_schedule_model   = None
_lstm_predictor:  LSTMPredictor | None = None


@app.on_event("startup")
async def _startup() -> None:
    global _schedule_model, _lstm_predictor
    model_dir = os.getenv("MODEL_DIR", os.path.join(os.path.dirname(__file__), "models"))
    _schedule_model = load_model(model_dir)

    # LSTM predictor — loads gracefully; stays None if model not trained yet
    _lstm_predictor = LSTMPredictor(
        model_path  = os.path.join(model_dir, "lstm_total_model.h5"),
        scaler_path = os.path.join(model_dir, "lstm_scaler.pkl"),
    )
    lstm_status = "ready" if _lstm_predictor.is_ready else "not trained (run train_lstm.py)"
    logger.info("Timeline service ready. Model dir: %s", model_dir)
    logger.info("LSTM predictor: %s", lstm_status)


# -- Request / Response schemas -----------------------------------------------
class PredictRequest(BaseModel):
    built_up_area_sqft:          float = Field(..., gt=0)
    num_floors:                  int   = Field(..., ge=1, le=10)
    num_rooms:                   int   = Field(..., ge=1)
    num_bathrooms:               int   = Field(1,   ge=1)
    district:                    str   = Field(...)
    construction_type:           str   = Field(...)
    soil_type:                   str   = Field(...)
    num_workers:                 int   = Field(..., ge=1)
    contractor_experience_years: float = Field(..., ge=0)
    total_cost_lkr:              float = Field(..., gt=0)
    labor_hours_total:           float = Field(None)
    material_cost_lkr:           float = Field(None)
    start_date:                  date  = Field(...)
    had_delays:                  int   = Field(0, ge=0, le=1)

    @field_validator("district")
    @classmethod
    def normalise_district(cls, v: str) -> str:
        return v.strip()

    @field_validator("construction_type")
    @classmethod
    def normalise_ctype(cls, v: str) -> str:
        return v.strip()

    @field_validator("soil_type")
    @classmethod
    def normalise_soil(cls, v: str) -> str:
        return v.strip().capitalize()

    model_config = {
        "json_schema_extra": {
            "example": {
                "built_up_area_sqft":          2000,
                "num_floors":                  2,
                "num_rooms":                   4,
                "num_bathrooms":               2,
                "district":                    "Colombo",
                "construction_type":           "Two-storey",
                "soil_type":                   "Medium",
                "num_workers":                 15,
                "contractor_experience_years": 8,
                "total_cost_lkr":              8500000,
                "labor_hours_total":           2000,
                "material_cost_lkr":           5000000,
                "start_date":                  "2026-06-01",
                "had_delays":                  0,
            }
        }
    }


class ProgressRequest(BaseModel):
    planned_weeks: dict[str, float] = Field(...)
    actual_weeks:  dict[str, float] = Field(...)

    model_config = {
        "json_schema_extra": {
            "example": {
                "planned_weeks": {
                    "Pre-Construction & Approvals": 4.0,
                    "Site Preparation": 2.0,
                    "Foundations": 3.5,
                    "Structure": 8.0,
                    "Envelope & Waterproofing": 4.0,
                    "MEP Rough-Ins": 3.0,
                    "Finishes": 5.0,
                    "External Works & Handover": 2.5,
                },
                "actual_weeks": {
                    "Pre-Construction & Approvals": 5.0,
                    "Foundations": 4.0,
                    "Structure": 10.0,
                },
            }
        }
    }


# -- Helper -------------------------------------------------------------------
def _build_phases_block(gantt_tasks: list[dict]) -> dict[str, dict]:
    return {
        task["id"]: {
            "predicted_weeks": task["duration_weeks"],
            "duration_days":   task["duration"],
            "start_date":      task["start_date"],
            "end_date":        task["end_date"],
            "is_critical":     task["is_critical"],
            "float_days":      task["float_days"],
            "dependencies":    task["dependencies"],
        }
        for task in gantt_tasks
    }


# -- Endpoints ----------------------------------------------------------------
@app.post("/predict", status_code=status.HTTP_200_OK)
async def predict(req: PredictRequest) -> dict[str, Any]:
    if _schedule_model is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Model not yet loaded - please retry in a few seconds.",
        )

    try:
        payload = req.model_dump()
        payload["start_date"] = req.start_date.isoformat()

        df_pre = _preprocessor.prepare(payload)
        df_pre["_start_month"] = req.start_date.month

        df_features = _feature_engineer.build_features(df_pre)

        phase_weeks: dict[str, float] = _schedule_model.predict_phase_durations(df_features)

        cp_result = _cp_engine.calculate(phase_weeks, req.start_date)

        phases_block = _build_phases_block(cp_result["gantt_tasks"])

        # ── LSTM total-duration prediction (additive; safe to fail) ──────────
        lstm_prediction: dict | None = None
        if _lstm_predictor is not None and _lstm_predictor.is_ready:
            # Build features dict: raw payload + start_month + encoded
            # categoricals already resolved by the preprocessor
            features_for_lstm: dict = dict(payload)
            features_for_lstm["start_month"] = req.start_date.month
            # Encoded categoricals live in df_pre after Preprocessor.prepare()
            for _col in (
                "district_enc",
                "construction_type_enc", "type_enc",
                "soil_type_enc",         "soil_enc",
            ):
                if _col in df_pre.columns:
                    features_for_lstm[_col] = float(df_pre[_col].iloc[0])

            lstm_result = _lstm_predictor.predict_total_weeks(
                phase_weeks=phase_weeks,
                features=features_for_lstm,
            )
            if lstm_result is not None:
                lstm_prediction = {
                    "total_weeks":         lstm_result["lstm_total_weeks"],
                    "confidence_interval": lstm_result["confidence_interval"],
                    "model":               "LSTM",
                }

        return {
            "phases":             phases_block,
            "total_weeks":        cp_result["total_duration_weeks"],
            "total_days":         cp_result["total_duration_days"],
            "project_start_date": cp_result["project_start_date"],
            "completion_date":    cp_result["project_end_date"],
            "critical_path":      cp_result["critical_path"],
            "gantt_tasks":        cp_result["gantt_tasks"],
            "model_used":         "ml_model",
            "lstm_prediction":    lstm_prediction,
        }

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("Unexpected error in /predict")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error - check server logs for details.",
        ) from exc


@app.post("/progress", status_code=status.HTTP_200_OK)
async def progress(req: ProgressRequest) -> dict[str, Any]:
    try:
        result = CriticalPathEngine.compute_deviation(
            req.planned_weeks,
            req.actual_weeks,
        )

        return {
            "phase_deviations":      result["phase_deviations"],
            "overall_deviation_pct": result["overall_deviation_pct"],
            "alert_level":           result["alert_level"],
            "phases_reported":       len(result["phase_deviations"]),
            "phases_total":          len(ALL_PHASES),
        }

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("Unexpected error in /progress")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error.",
        ) from exc


@app.get("/health", status_code=status.HTTP_200_OK)
async def health() -> dict[str, Any]:
    model_loaded = _schedule_model is not None
    lstm_ready   = _lstm_predictor is not None and _lstm_predictor.is_ready
    return {
        "status":        "ok",
        "service":       "timeline-generation",
        "version":       "2.0.0",
        "model_loaded":  model_loaded,
        "lstm_ready":    lstm_ready,
        "phases":        ALL_PHASES,
    }


# -- Dev entry-point ----------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        reload=True,
    )
