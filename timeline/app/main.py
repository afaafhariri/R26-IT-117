"""FastAPI application for the Project Management & Timeline Prediction component."""

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

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5500",
        "http://localhost:5500",
        "http://127.0.0.1:8000",
        "http://localhost:8000",
        "null",
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
