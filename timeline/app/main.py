"""FastAPI application for the Project Management & Timeline Prediction component."""

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routes.timeline_routes import router as timeline_router
from app.utils.response_utils import health_response


settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "AI-based construction timeline and project management planning backend. "
        "This backend receives Cost Estimation Component JSON as input, predicts "
        "phase-wise construction durations using XGBoost, predicts total duration "
        "using PyTorch LSTM, and generates Gantt chart data, milestones, critical "
        "path, task dependencies, basic resource allocation, and a planned schedule "
        "payload for the Performance Monitoring & Delay Prediction Component. "
        "This backend does not perform cost estimation, actual site monitoring, "
        "delay prediction, progress tracking, or delay risk analysis."
    ),
)

# The planner UI (Vite dev server, :5173) calls this service directly from the
# browser, so its origin has to be allowed. Override the whole list with
# CORS_ALLOW_ORIGINS (comma-separated) for other deployments.
_DEFAULT_CORS_ORIGINS = [
    "http://127.0.0.1:5173",
    "http://localhost:5173",
    "http://127.0.0.1:5500",
    "http://localhost:5500",
    "http://127.0.0.1:8000",
    "http://localhost:8000",
    "null",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        o.strip()
        for o in os.getenv("CORS_ALLOW_ORIGINS", ",".join(_DEFAULT_CORS_ORIGINS)).split(",")
        if o.strip()
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", tags=["Health Check"])
def root() -> dict[str, str]:
    """Health check endpoint."""

    return health_response()


app.include_router(timeline_router)
