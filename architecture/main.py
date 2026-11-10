"""Component 01 — AI-Based Architectural Planning API.

FastAPI application entry point for the 4-stage cadastral plan processing pipeline.
"""

import os

os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")  # force CPU

from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

# Load architecture/.env (the same file the Celery worker reads) before any
# module reads os.getenv().
load_dotenv(Path(__file__).resolve().parent / ".env")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import cadastral, design, floorplans, pipeline_v1, video
from utils.file_handler import FileHandler
from utils.logger import get_logger

_logger = get_logger("main")

# ---------------------------------------------------------------------------
# Lifespan (startup warm-up)
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    _logger.info("C01 Architectural Planning API starting up (version=0.1.0)")

    schema_dir = Path(os.getenv("SCHEMA_DIR", "shared/schemas"))
    if schema_dir.exists():
        file_handler = FileHandler()
        for schema_file in schema_dir.glob("*.json"):
            try:
                file_handler.load_schema(schema_file.name)
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

# Job-based routes used by the web app (via the gateway)
app.include_router(cadastral.router, prefix="/api")
app.include_router(floorplans.router, prefix="/api")
app.include_router(design.router, prefix="/api")
app.include_router(video.router, prefix="/api")
# Stage-by-stage pipeline routes
app.include_router(pipeline_v1.router)
