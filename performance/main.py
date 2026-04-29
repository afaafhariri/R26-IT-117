"""
Component 03 — Performance Monitor
Project R26-IT-117: AI-Driven Construction Planner

FastAPI entry point. Starts the Kafka consumer as a background thread
and exposes REST endpoints for project monitoring, alerts, and
productivity analysis.
"""

import os
import asyncio
import threading
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

import redis.asyncio as aioredis
from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from ingestion.kafka_consumer import ProgressKafkaConsumer
from ingestion.progress_normaliser import ProgressNormaliser
from pipeline.preprocessor import Preprocessor
from pipeline.feature_engineer import FeatureEngineer
from pipeline.delay_model import DelayPredictor
from pipeline.alert_engine import AlertEngine
from monitoring.productivity_analyser import ProductivityAnalyser
from monitoring.dashboard_feed import GrafanaDashboardFeed

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pydantic v2 request / response models
# ---------------------------------------------------------------------------

class ProjectInitRequest(BaseModel):
    """Payload for POST /project/init."""
    project_id: str = Field(..., description="Unique project identifier")
    building_schema: dict[str, Any] = Field(..., description="Building Schema JSON from Component 01")
    cost_report: dict[str, Any] = Field(..., description="Cost Report JSON from Component 02")


class ProgressUpdateRequest(BaseModel):
    """Payload for POST /progress (manual entry)."""
    project_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    phase: str
    planned_completion_pct: float = Field(..., ge=0.0, le=100.0)
    actual_completion_pct: float = Field(..., ge=0.0, le=100.0)
    labour_count: int = Field(..., ge=0)
    material_deliveries: int = Field(..., ge=0)
    weather_delay_days: int = Field(..., ge=0)
    rework_incidents: int = Field(..., ge=0)


class ProjectStatusResponse(BaseModel):
    project_id: str
    delay_risk: str
    predicted_delay_days: int
    confidence: float
    primary_cause: str
    schedule_performance_index: float
    timestamp: datetime


class AlertResponse(BaseModel):
    alert_id: str
    project_id: str
    type: str
    severity: str
    message: str
    timestamp: datetime
    recommended_action: str


class ProductivityResponse(BaseModel):
    overall_spi: float
    phase_breakdown: list[dict[str, Any]]
    labour_efficiency_index: float
    projected_completion_date: str
    days_ahead_or_behind: int


# ---------------------------------------------------------------------------
# Application state (shared between routes and background threads)
# ---------------------------------------------------------------------------

class AppState:
    """Holds shared runtime objects initialised at startup."""
    redis_client: aioredis.Redis | None = None
    kafka_thread: threading.Thread | None = None
    project_registry: dict[str, dict] = {}      # project_id -> {schema, cost_report}
    progress_store: dict[str, list] = {}         # project_id -> [normalised records]


app_state = AppState()


# ---------------------------------------------------------------------------
# Lifespan — startup / shutdown
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise Redis and start the Kafka consumer thread on startup."""
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    app_state.redis_client = aioredis.from_url(redis_url, decode_responses=True)
    logger.info("Redis connected: %s", redis_url)

    consumer = ProgressKafkaConsumer(
        bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"),
        app_state=app_state,
    )
    app_state.kafka_thread = threading.Thread(
        target=consumer.start, daemon=True, name="kafka-consumer"
    )
    app_state.kafka_thread.start()
    logger.info("Kafka consumer thread started")

    yield  # application runs here

    await app_state.redis_client.aclose()
    logger.info("Redis connection closed")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Component 03 — Performance Monitor",
    description="Real-time construction site progress monitoring and delay prediction.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Dependency helpers
# ---------------------------------------------------------------------------

def get_normaliser() -> ProgressNormaliser:
    return ProgressNormaliser()


def get_predictor() -> DelayPredictor:
    return DelayPredictor()


def get_alert_engine() -> AlertEngine:
    return AlertEngine(redis_client=app_state.redis_client)


def get_productivity_analyser() -> ProductivityAnalyser:
    return ProductivityAnalyser()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.post("/project/init", status_code=201, summary="Initialise monitoring for a project")
async def init_project(body: ProjectInitRequest) -> dict:
    """
    Register a project for monitoring. Stores the Building Schema and Cost Report
    as the planning baseline used by the feature engineering and prediction pipeline.
    """
    app_state.project_registry[body.project_id] = {
        "building_schema": body.building_schema,
        "cost_report": body.cost_report,
        "registered_at": datetime.now(timezone.utc).isoformat(),
    }
    app_state.progress_store.setdefault(body.project_id, [])

    logger.info("Project %s initialised for monitoring", body.project_id)
    return {
        "project_id": body.project_id,
        "status": "monitoring_active",
        "message": "Project registered. Kafka consumer will ingest progress updates.",
    }


@app.post("/progress", status_code=202, summary="Submit a manual progress update")
async def submit_progress(
    body: ProgressUpdateRequest,
    background_tasks: BackgroundTasks,
    normaliser: ProgressNormaliser = Depends(get_normaliser),
    predictor: DelayPredictor = Depends(get_predictor),
    alert_engine: AlertEngine = Depends(get_alert_engine),
) -> dict:
    """
    Accept a manual progress entry (mirrors the Kafka message schema).
    Runs normalisation, feature engineering, delay prediction, and alert
    evaluation in the background so the HTTP response is non-blocking.
    """
    if body.project_id not in app_state.project_registry:
        raise HTTPException(status_code=404, detail="Project not initialised. Call POST /project/init first.")

    raw = body.model_dump()
    background_tasks.add_task(
        _process_progress_record, raw, normaliser, predictor, alert_engine
    )
    return {"status": "accepted", "project_id": body.project_id}


@app.get(
    "/project/{project_id}/status",
    response_model=ProjectStatusResponse,
    summary="Current delay risk and schedule deviation",
)
async def get_project_status(
    project_id: str,
    predictor: DelayPredictor = Depends(get_predictor),
) -> ProjectStatusResponse:
    """Return the latest delay prediction for the given project."""
    records = app_state.progress_store.get(project_id)
    if not records:
        raise HTTPException(status_code=404, detail="No progress data found for project.")

    baseline = app_state.project_registry.get(project_id, {})
    fe = FeatureEngineer()
    preprocessor = Preprocessor()

    import pandas as pd
    df = preprocessor.fit_transform(records)
    features = fe.build_features(
        df,
        baseline.get("building_schema", {}),
        baseline.get("cost_report", {}),
    )

    prediction = predictor.predict(features)
    latest = records[-1]

    return ProjectStatusResponse(
        project_id=project_id,
        delay_risk=prediction["delay_risk"],
        predicted_delay_days=prediction["predicted_delay_days"],
        confidence=prediction["confidence"],
        primary_cause=prediction["primary_cause"],
        schedule_performance_index=latest.get("schedule_performance_index", 1.0),
        timestamp=datetime.now(timezone.utc),
    )


@app.get(
    "/project/{project_id}/alerts",
    response_model=list[AlertResponse],
    summary="Active alerts for the project",
)
async def get_project_alerts(project_id: str) -> list[AlertResponse]:
    """Retrieve active alerts from the Redis cache for the given project."""
    if app_state.redis_client is None:
        raise HTTPException(status_code=503, detail="Redis unavailable.")

    channel = f"alerts.{project_id}"
    # TODO: Replace with a persistent alert store (e.g. TimescaleDB query).
    #       For now, read the latest cached alert list from Redis.
    raw = await app_state.redis_client.lrange(channel, 0, 49)
    import json
    alerts = [json.loads(a) for a in raw]
    return [AlertResponse(**a) for a in alerts]


@app.get(
    "/project/{project_id}/productivity",
    response_model=ProductivityResponse,
    summary="Productivity metrics for the project",
)
async def get_productivity(
    project_id: str,
    analyser: ProductivityAnalyser = Depends(get_productivity_analyser),
) -> ProductivityResponse:
    """Return aggregated productivity metrics computed from stored progress records."""
    records = app_state.progress_store.get(project_id)
    if not records:
        raise HTTPException(status_code=404, detail="No progress data found for project.")

    result = analyser.analyse(records)
    return ProductivityResponse(**result)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _process_progress_record(
    raw: dict,
    normaliser: ProgressNormaliser,
    predictor: DelayPredictor,
    alert_engine: AlertEngine,
) -> None:
    """
    Full pipeline: normalise → preprocess → feature engineering →
    delay prediction → alert evaluation.
    Runs in a FastAPI background task (non-blocking).
    """
    try:
        normalised = normaliser.normalise(raw)
        project_id = normalised["project_id"]

        app_state.progress_store.setdefault(project_id, []).append(normalised)

        baseline = app_state.project_registry.get(project_id, {})
        fe = FeatureEngineer()
        preprocessor = Preprocessor()

        import pandas as pd
        records = app_state.progress_store[project_id]
        df = preprocessor.fit_transform(records)
        features = fe.build_features(
            df,
            baseline.get("building_schema", {}),
            baseline.get("cost_report", {}),
        )

        prediction = predictor.predict(features)
        alerts = alert_engine.evaluate(prediction, normalised)

        for alert in alerts:
            await alert_engine.publish_alert(alert)

        logger.info("Processed progress record for project %s — risk: %s", project_id, prediction["delay_risk"])

    except Exception as exc:
        logger.exception("Error processing progress record: %s", exc)
