"""Component 02 — Cost Estimation API.

Five-layer pipeline:
  Layer 1 (BOQ Engine)         → structural, finishing, and services quantities
  Layer 2 (Rate Engine)        → ICTAD unit rates + district adjustment + escalation
  Layer 3 (ML Prediction)      → XGBoost with 90% confidence interval
  Layer 4 (Risk Adjuster)      → risk scoring, contingency build-up, report assembly

Endpoints:
  POST /estimate               Full 5-layer cost report
  POST /boq                    BOQ quantities only (Layer 1)
  GET  /rates/{district}       ICTAD rates for a district (Layer 2)
  POST /retrain                Trigger model retraining (admin-only)
"""

import logging
import os
from datetime import date
from typing import Any, Optional

from fastapi import FastAPI, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from layers.layer1_boq.boq_engine import BOQEngine
from layers.layer2_rate_engine.rate_engine import RateEngine
from layers.layer3_ml_prediction.feature_engineer import FeatureEngineer
from layers.layer3_ml_prediction.ensemble import EnsembleCostPredictor
from layers.layer3_ml_prediction.shap_explainer import SHAPExplainer
from layers.layer4_risk_adjuster.risk_scorer import RiskScorer
from layers.layer4_risk_adjuster.contingency import ContingencyCalculator
from layers.layer4_risk_adjuster.report_builder import ReportBuilder

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="AI-Driven Construction Planner — Component 02: Cost Estimation",
    version="1.0.0",
    description="5-layer cost estimation pipeline for Project R26-IT-117.",
)

# ---------------------------------------------------------------------------
# Shared pipeline instances (initialised once at startup)
# ---------------------------------------------------------------------------

_boq_engine = BOQEngine()
_rate_engine = RateEngine()
_feature_engineer = FeatureEngineer()
_ensemble = EnsembleCostPredictor(auto_load=True)
_shap_explainer = SHAPExplainer(top_n=5)
_risk_scorer = RiskScorer()
_contingency_calc = ContingencyCalculator()
_report_builder = ReportBuilder()


# ---------------------------------------------------------------------------
# Pydantic v2 request / response models
# ---------------------------------------------------------------------------

class RoomCounts(BaseModel):
    living_room: int = Field(default=1, ge=0)
    master_bedroom: int = Field(default=1, ge=0)
    bedroom: int = Field(default=2, ge=0)
    kitchen: int = Field(default=1, ge=0)
    bathroom: int = Field(default=2, ge=0)
    dining_room: int = Field(default=1, ge=0)
    study: int = Field(default=0, ge=0)
    garage: int = Field(default=0, ge=0)


class BuildingSchema(BaseModel):
    """Input Building Schema produced by Component 01."""

    # Geometry
    footprint_sqm: float = Field(..., gt=0, description="Ground-floor footprint in m²")
    perimeter: float = Field(..., gt=0, description="External perimeter in metres")
    floors: int = Field(default=1, ge=1, le=10)
    floor_height: float = Field(default=3.0, gt=0, description="Floor-to-floor height in metres")
    wall_height: float = Field(default=3.0, gt=0)
    excavation_depth: float = Field(default=1.5, gt=0)

    # Structural
    column_count: int = Field(default=0, ge=0, description="0 = auto-derived from perimeter")
    openings_sqm: float = Field(default=0.0, ge=0, description="Total door + window area in m²")
    internal_wall_length: float = Field(default=0.0, ge=0)

    # Finishing
    finish_grade: str = Field(default="mid", description="economy | mid | luxury")
    roof_type: str = Field(default="gable", description="flat | gable | hip | mansard")

    # Site / location
    district: str = Field(..., description="Sri Lankan district name")
    is_coastal: bool = Field(default=False)
    terrain: str = Field(default="flat", description="flat | sloped | hilly | rocky")
    road_access: str = Field(default="paved", description="paved | gravel | track | none")
    plot_area: float = Field(default=500.0, gt=0, description="Total plot area in m²")

    # Rooms
    rooms: RoomCounts = Field(default_factory=RoomCounts)
    bathroom_count: int = Field(default=2, ge=0)
    room_count: int = Field(default=4, ge=1)

    # Dates for rate escalation
    base_rate_date: str = Field(default="2024-10-01", description="ISO date for ICTAD base rates")
    target_date: Optional[str] = Field(default=None, description="ISO projection date (defaults to today)")

    @field_validator("finish_grade")
    @classmethod
    def validate_finish_grade(cls, v: str) -> str:
        allowed = {"economy", "mid", "luxury"}
        if v.lower() not in allowed:
            raise ValueError(f"finish_grade must be one of {allowed}")
        return v.lower()

    @field_validator("terrain")
    @classmethod
    def validate_terrain(cls, v: str) -> str:
        allowed = {"flat", "sloped", "hilly", "rocky"}
        return v.lower() if v.lower() in allowed else "flat"

    def to_dict(self) -> dict:
        """Return a plain dict including rooms as a primitive dict."""
        d = self.model_dump()
        d["rooms"] = self.rooms.model_dump()
        return d


class EstimateResponse(BaseModel):
    estimate_id: str
    generated_at: str
    summary: dict[str, Any]
    boq_summary: dict[str, Any]
    trade_breakdown: dict[str, Any]
    contingency_breakdown: list[Any]
    risk_factors_applied: list[Any]
    shap_top_drivers: list[Any]
    model_metadata: dict[str, Any]
    rate_metadata: dict[str, Any]
    feeds_downstream: dict[str, Any]


class BOQResponse(BaseModel):
    structural: dict[str, Any]
    finishing: dict[str, Any]
    services: dict[str, Any]
    summary: dict[str, Any]


class RetrainResponse(BaseModel):
    status: str
    message: str


# ---------------------------------------------------------------------------
# Admin dependency
# ---------------------------------------------------------------------------

def require_admin(x_admin_key: str = Header(default="")):
    """Validate the X-Admin-Key header for protected endpoints."""
    admin_key = os.getenv("ADMIN_API_KEY", "")
    if not admin_key or x_admin_key != admin_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing X-Admin-Key header.",
        )


# ---------------------------------------------------------------------------
# Pipeline helper
# ---------------------------------------------------------------------------

def _run_full_pipeline(schema: BuildingSchema) -> dict:
    """Execute all four layers and return the assembled Cost Report dict."""
    schema_dict = schema.to_dict()
    finish_grade = schema.finish_grade

    # Layer 1 — BOQ
    boq = _boq_engine.run(schema_dict)

    # Layer 2 — Rate Engine
    target_date = schema.target_date or str(date.today())
    rates = _rate_engine.price_boq(
        boq,
        district=schema.district,
        base_date=schema.base_rate_date,
        target_date=target_date,
    )

    # Layer 3 — ML Prediction
    X = _feature_engineer.build_features(boq, schema_dict, finish_grade)
    prediction = _ensemble.predict(X)

    # Add SHAP explanations to the prediction dict
    shap_results = _shap_explainer.explain(_ensemble._xgb, X)
    prediction["shap_explanations"] = shap_results

    # Layer 4 — Risk + Contingency + Report
    risk = _risk_scorer.score(schema_dict, schema_dict, finish_grade)
    direct_cost = rates.get("direct_cost_lkr", 0.0)
    contingency = _contingency_calc.calculate(direct_cost, risk["total_risk_pct"])
    report = _report_builder.build(boq, rates, prediction, risk, contingency)

    return report


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.post("/estimate", response_model=EstimateResponse, summary="Full 5-layer cost estimate")
async def estimate(schema: BuildingSchema) -> dict:
    """Accept a Building Schema JSON and return a full Cost Report.

    The report includes BOQ breakdown, priced trade items, ML ensemble prediction,
    90% confidence interval, risk factors, SHAP cost drivers, and downstream feeds.
    """
    try:
        return _run_full_pipeline(schema)
    except Exception as exc:
        logger.exception("Pipeline error in /estimate: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/boq", response_model=BOQResponse, summary="BOQ quantities only (Layer 1)")
async def boq(schema: BuildingSchema) -> dict:
    """Return Layer 1 BOQ quantities without pricing or ML prediction."""
    try:
        return _boq_engine.run(schema.to_dict())
    except Exception as exc:
        logger.exception("Pipeline error in /boq: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/rates/{district}", summary="ICTAD rates for a district (Layer 2)")
async def get_rates(district: str) -> dict:
    """Return the current ICTAD unit rate schedule with district multiplier applied."""
    try:
        return _rate_engine.get_district_rates(district)
    except Exception as exc:
        logger.exception("Error fetching rates for district '%s': %s", district, exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.post(
    "/retrain",
    response_model=RetrainResponse,
    summary="Trigger model retraining (admin only)",
    dependencies=[Depends(require_admin)],
)
async def retrain() -> dict:
    """Trigger a background retraining job for the XGBoost model.

    Requires the X-Admin-Key header matching the ADMIN_API_KEY environment variable.

    TODO: Implement actual training data pull from PostgreSQL and background task.
    """
    logger.info("Retraining triggered via API.")
    # TODO: run tests/generate_dataset.py then scripts/train_model.py
    return {
        "status": "accepted",
        "message": "Model retraining job queued. Check logs for progress.",
    }


@app.get("/health", summary="Health check")
async def health() -> dict:
    """Simple liveness check."""
    return {"status": "ok", "component": "02-cost-estimation"}
