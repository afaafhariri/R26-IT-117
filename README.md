# R26-IT-117 — AI-Driven Construction Planner for Sri Lankan Residential Buildings

This document combines all four components of the system in pipeline order:
1. [Architectural Planning](#component-01--architectural-planning-api)
2. [Cost Estimation](#component-02--cost-estimation-service)
3. [Project Management & Timeline Prediction](#component-03--project-management--timeline-prediction)
4. [Performance Monitoring](#component-04--construction-performance-monitoring-and-delay-prediction)

---

## Repository Layout

```
R26-IT-117/
├── Architecture/       # Component 01 — Architectural Planning API      (FastAPI, :8001)
├── cost-estimation/    # Component 02 — Cost Estimation Service         (FastAPI, :8002)
├── timeline/           # Component 03 — Timeline Prediction              (FastAPI, :8000)
├── performance/        # Component 04 — Performance Monitoring          (Flask,   :5004)
├── frontend/           # Static single-file API test UI for Component 04
├── gateway/            # Route definitions shared across services
├── shared/
│   └── schemas/        # site_schema.json, building_schema.json — the C01→C02 contract
├── research/           # Notebooks and datasets
└── docker-compose.yml  # postgres + performance
```

Component 01 also ships its own React + TypeScript client at
`Architecture/frontend/` (the CadaPlan UI). The top-level `frontend/` directory
is a separate, single-file test page for Component 04 — the two are unrelated
despite the similar names.

### Data flow

```
Cadastral plan  →  C01 Architecture  →  BuildingSchema  →  C02 Cost Estimation
                                                    ↓
                        C04 Performance  ←  C03 Timeline
```

### Docker Compose coverage

`docker-compose.yml` currently defines only two services — `postgres` and
`performance`. Components 01, 02 and 03 each have their own `Dockerfile` but
are not yet added to the compose file, so they must be run individually. See
each component's *Running Locally* section.

---

# Component 01 — Architectural Planning API

**Project:** R26-IT-117 — AI-Driven Construction Planner for Sri Lankan Residential Construction  
**Service Port:** `8001`  
**API Version:** `v0.1.0`

---

## Overview

Component 01 is a FastAPI microservice that turns a Sri Lankan cadastral plan upload (PDF or image) into a fully validated Building Schema ready for downstream cost estimation (Component 02). It implements a **6-stage pipeline** — Extraction → Buildable Zone → Floor Plan Generation → Rendering → Visualisation → Packaging. Stages 1-4 are exposed as independent REST endpoints under `/api/v1`; stages 5-6 are driven by the newer job-based routers under `/api`.

The pipeline is built around Sri Lankan-specific constraints: NBC setback and BCR rules per district, SLD99 coordinate parsing, and a custom SpaCy NER model trained on local deed formats. Floor plans are generated asynchronously via Celery, using three parallel Gemini LLM calls at different creativity temperatures, then validated geometrically and scored before being returned.

---

## Table of Contents

1. [Pipeline Architecture](#pipeline-architecture)
2. [Directory Structure](#directory-structure)
3. [API Endpoints](#api-endpoints)
4. [Request & Response Models](#request--response-models)
5. [Environment Variables](#environment-variables)
6. [Dependencies](#dependencies)
7. [JSON Schemas](#json-schemas)
8. [Running Locally](#running-locally)
9. [Running with Docker](#running-with-docker)
10. [Testing](#testing)
11. [Key Design Decisions](#key-design-decisions)
12. [MLOps & Model Utilities](#mlops--model-utilities)
13. [Inter-Component Integration](#inter-component-integration)

---

## Pipeline Architecture

```
[Cadastral Plan Upload]
        │
        ▼
┌─────────────────────────────────────────────────────────┐
│  Stage 1 — Extraction                POST /extract      │
│                                                         │
│  PDF/Image → EasyOCR → CNN Classifier → OpenCV         │
│  Boundary Detector → SpaCy NER → SchemaAssembler        │
│                     ↓                                   │
│              SiteSchema (validated JSON)                │
└─────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────┐
│  Stage 2 — Buildable Zone       POST /buildable-zone    │
│                                                         │
│  NBC Constraint Engine (setbacks, BCR, coastal) →       │
│  Shapely Polygon Buffering → Orientation Solver         │
│                     ↓                                   │
│          BuildableZone (footprint + orientation)        │
└─────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────┐
│  Stage 3 — Floor Plan Generation  POST /generate        │
│            (Async via Celery)     GET  /status/{id}     │
│                                                         │
│  Supabase pgvector RAG → Prompt Builder →               │
│  3× Gemini (T=0.4 / 0.7 / 1.0) → Layout Solver →       │
│  Geometric Validator → Scorer                           │
│                     ↓                                   │
│      3 Alternatives: conservative / balanced / creative │
└─────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────┐
│  Stage 4 — Render                   POST /render        │
│                                                         │
│  SVGRenderer → PDFRenderer → SchemaSerialiser           │
│                     ↓                                   │
│  SVG file + 6-page PDF + BuildingSchema (→ C02)         │
└─────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────┐
│  Stage 5 — Visualisation      POST /api/generate-video  │
│                                                         │
│  Local Pillow renderers (blueprint + isometric 3D) and  │
│  optional Gemini image / text / video generation        │
│                     ↓                                   │
│      Blueprint PNG, isometric view, optional video      │
└─────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────┐
│  Stage 6 — Packaging                                    │
│                                                         │
│  PackageAssembler collects every upstream stage output  │
│                     ↓                                   │
│               FullDesignPackage                         │
└─────────────────────────────────────────────────────────┘
```

---

## Directory Structure

```
Architecture/
├── main.py                         # FastAPI app, all route definitions
├── requirements.txt                # Python dependencies (Python 3.11)
├── Dockerfile                      # Container build (Python 3.11-slim, port 8001)
├── .env                            # Local environment variables (not committed)
│
├── stages/
│   ├── stage1_extraction/
│   │   ├── ocr_engine.py           # EasyOCR wrapper → tokens + raw_text + page_dimensions
│   │   ├── cnn_classifier.py       # CNN (rule-based fallback) → plan_type + confidence
│   │   ├── boundary_detector.py    # OpenCV edge detection → normalised [0,1] polygon
│   │   ├── ner_parser.py           # SpaCy NER + regex → cadastral field extraction
│   │   └── schema_assembler.py     # Assembles & validates SiteSchema
│   │
│   ├── stage2_buildable_zone/
│   │   ├── nbc_constraints.py      # NBC setbacks + BCR per district + coastal adjustments
│   │   ├── polygon_calculator.py   # Shapely inward buffer → buildable polygon + areas
│   │   └── orientation_solver.py   # Entrance side + solar orientation in degrees
│   │
│   ├── stage3_floor_plan/
│   │   ├── rag_retriever.py        # Supabase pgvector retrieval (hardcoded fallback norms)
│   │   ├── prompt_builder.py       # 4-part structured Gemini prompt
│   │   ├── llm_generator.py        # 3 parallel Gemini calls (T=0.4, 0.7, 1.0)
│   │   ├── layout_solver.py        # Strip-packing overlap elimination
│   │   ├── validator.py            # Geometric + NBC programmatic checks
│   │   └── scorer.py               # 4-dimension quality scoring
│   │
│   └── stage4_renderer/
│       ├── svg_renderer.py         # svgwrite: rooms, furniture, dimensions, scale bar, north arrow
│       ├── pdf_renderer.py         # ReportLab: 6-page professional document
│       └── schema_serialiser.py    # Flat BuildingSchema for C02 handoff
│   │
│   ├── stage5_visualization/
│   │   ├── local_blueprint_renderer.py  # Pillow 2D blueprint (cost-free)
│   │   ├── local_isometric_renderer.py  # Pillow isometric 3D dollhouse view
│   │   ├── gemini_image_gen.py     # Gemini image generation
│   │   ├── gemini_text_gen.py      # gemini-2.5-flash text generation
│   │   ├── gemini_video_gen.py     # veo-2.0-generate-001 video generation
│   │   └── prompt_templates.py     # Prompt factories for the Gemini calls
│   │
│   └── stage6_packager/
│       └── package_assembler.py    # Assembles FullDesignPackage from stages 1-5
│
├── routers/                        # Job-based API surface, mounted at /api
│   ├── cadastral.py                # POST /process-cadastral
│   ├── floorplans.py               # POST /generate-floorplans, GET /floorplans/status/{job_id}
│   ├── design.py                   # POST /select-plan
│   └── video.py                    # POST /generate-video
│
├── frontend/                       # CadaPlan React + TypeScript + Vite client
│   ├── src/                        # Views, components, apiService
│   ├── package.json
│   └── vite.config.ts
│
├── tasks/
│   └── celery_app.py               # Celery app (Redis broker/backend) + async floor plan task
│
├── utils/
│   ├── logger.py                   # JSON-structured stdout logger (component: C01)
│   ├── file_handler.py             # Temp file I/O + schema caching
│   └── coord_converter.py          # SLD99 (EPSG:5234) → WGS84 (EPSG:4326) conversion
│
├── models/
│   └── ner_cadastral/              # Fine-tuned SpaCy NER model
│       ├── config.cfg
│       └── ner/, tok2vec/, vocab/, tokenizer/, ...
│
├── data/                           # NER training corpus (12 MB, C01-only)
│   ├── cadastral_plans/            # 69 source survey plan PDFs
│   ├── ocr_results/                # 129 JSON — 69 OCR'd + 60 synthetic
│   └── spacy_training/
│       └── train.spacy             # Compiled training file for train_ner.py
│
├── knowledge_base/
│   ├── embedder.py                 # sentence-transformers embedding wrapper
│   ├── ingest.py                   # Vector DB ingestion pipeline
│   └── corpus/
│       └── sl_design_norms.md      # Sri Lankan residential design standards reference
│
├── tests/
│   ├── conftest.py                 # Shared pytest fixtures (Plan No. 2362, Ampara sample)
│   ├── test_extraction.py          # Stage 1 tests
│   ├── test_buildable_zone.py      # Stage 2 tests
│   ├── test_generator.py           # Stage 3 tests
│   └── plan_2362.jpg               # Sample test image (Ampara, 472.9 sqm, coastal)
│
└── [ML / utility scripts]
    ├── train_ner.py                # Custom NER model training
    ├── convert_to_spacy.py         # Annotation → SpaCy training format
    ├── batch_ocr.py                # Bulk OCR processing
    ├── benchmark_models.py         # Model evaluation metrics
    ├── benchmark_results.csv       # Evaluation results table
    ├── generate_synthetic.py       # Synthetic data for NER augmentation
    ├── seed_from_images.py         # Bootstrap vector DB from plan images
    ├── seed_plans.py               # Load sample plans into vector DB
    ├── embed_plans.py              # Full vector embedding pipeline
    └── review_annotations.py       # Visual review of NER labeled data
```

---

## API Endpoints

All endpoints are prefixed with `/api/v1`. Interactive documentation is available at `http://localhost:8001/docs`.

### `GET /api/v1/health`

Health check.

**Response:**
```json
{ "status": "healthy", "component": "C01", "version": "0.1.0" }
```

---

### `POST /api/v1/extract` — Stage 1

Accepts a cadastral plan file and returns a validated Site Schema.

| Field | Value |
|-------|-------|
| **Content-Type** | `multipart/form-data` |
| **Accepted formats** | PDF, JPEG, PNG, TIFF |
| **Max file size** | 50 MB |

**Process:**
1. PDF pages are rendered to PNG via PyMuPDF.
2. EasyOCR extracts text tokens and page dimensions.
3. CNN classifier validates the document is a cadastral plan.
4. OpenCV detects the boundary polygon (coordinates normalised to [0, 1]).
5. SpaCy NER + regex parse plan number, district, area, SLD99 coordinates, and other fields.
6. `SchemaAssembler` validates the result against `site_schema.json`.

**Response:** `SiteSchemaResponse` — see [Request & Response Models](#request--response-models).

---

### `POST /api/v1/buildable-zone` — Stage 2

Computes the legally buildable area given a Site Schema and setback parameters.

**Process:**
1. `NBCConstraintEngine` looks up NBC setbacks by road type and BCR by district (with coastal adjustment).
2. `BuildableZoneCalculator` applies Shapely negative buffering on the normalised polygon and scales back to real square metres.
3. `OrientationSolver` determines the entrance side and recommended solar orientation.

**Request body:** `BuildableZoneRequest`  
**Response:** `BuildableZoneResponse`

---

### `POST /api/v1/generate-floor-plan` — Stage 3 (async)

Dispatches an asynchronous Celery task for floor plan generation. Returns immediately with a `task_id`.

**Process (inside Celery worker):**
1. `RAGRetriever` queries Supabase pgvector for similar Sri Lankan residential layouts (falls back to hardcoded design norms if unavailable).
2. `PromptBuilder` constructs a structured 4-part prompt.
3. `FloorPlanGenerator` fires 3 parallel Gemini requests at temperatures 0.4 (conservative), 0.7 (balanced), and 1.0 (creative).
4. `solve_overlaps()` resolves any spatial conflicts via strip-packing.
5. `LayoutValidator` checks geometric and NBC constraints.
6. `LayoutScorer` scores each alternative across 4 dimensions.

**Request body:** `FloorPlanRequest`  
**Response:**
```json
{ "task_id": "uuid4", "status": "pending" }
```

---

### `GET /api/floorplans/status/{job_id}` — Stage 3 (poll)

Polls the Celery result backend for the job status. Note this route lives on
the `floorplans` router and is mounted under `/api`, **not** `/api/v1`.

**Status values:** `pending` | `processing` | `complete` | `failed`

**Response when complete:** `TaskStatusResponse` containing all 3 floor plan alternatives with scores.

---

### `POST /api/v1/render` — Stage 4

Renders the selected floor plan to SVG and PDF, serialises the Building Schema, and fires a non-blocking POST to Component 02.

**Process:**
1. `SVGRenderer` draws rooms with colour coding, furniture symbols, dimension lines, scale bar, and north arrow.
2. `PDFRenderer` wraps the SVG into a 6-page professional document using ReportLab.
3. `SchemaSerialiser` flattens all pipeline outputs into a Building Schema validated against `building_schema.json`.
4. Fire-and-forget POST to `${C02_BASE_URL}/estimate` — failure is logged but never raises.

**Request body:** `RenderRequest`  
**Response:** `RenderResponse` with file paths, download URLs, and the full Building Schema.

---

### `GET /api/v1/download/{filename}`

Downloads a rendered SVG or PDF from the temp directory.

**Query param:** `dir` (optional) — subdirectory within `TEMP_FILES_DIR`.

---

### Job-based routers (mounted at `/api`)

A second, newer API surface drives the stage 5-6 work as background jobs. These
routers are registered in `main.py` with `prefix="/api"`.

| Method | Path | Router | Description |
|--------|------|--------|-------------|
| `POST` | `/api/process-cadastral` | `cadastral.py` | Upload and process a cadastral plan as a job |
| `POST` | `/api/generate-floorplans` | `floorplans.py` | Kick off asynchronous floor plan generation |
| `GET` | `/api/floorplans/status/{job_id}` | `floorplans.py` | Poll job status |
| `POST` | `/api/select-plan` | `design.py` | Select one of the generated alternatives |
| `POST` | `/api/generate-video` | `video.py` | Stage 5 video generation (rate limited) |

> **Note —** rendered SVG and PDF artefacts are served by
> `GET /api/v1/download/{filename}` (Stage 4), which reads from the per-render
> output directory. An earlier `routers/downloads.py` expected job-keyed files
> in `TEMP_FILES_DIR` that no code path ever wrote; it was never registered and
> has been removed.

---

## Request & Response Models

### Input Models

#### `SetbackInputs`
```json
{
  "road_type": "national_road | provincial | local | lane",
  "front_setback_m": 3.0,
  "rear_setback_m": 1.5,
  "side_setback_m": 1.0,
  "coverage_ratio": 0.6,
  "floors_requested": 2
}
```

#### `BuildableZoneRequest`
```json
{
  "site_schema": { ... },
  "setback_inputs": { ... }
}
```

#### `UserRequirements`
```json
{
  "room_types": ["living", "dining", "kitchen", "master_bedroom", "bedroom", "bathroom"],
  "room_count": 4,
  "garage": true,
  "floors": 2,
  "budget_tier": "economy | medium | luxury",
  "style": "modern | traditional | contemporary",
  "district": "Ampara",
  "is_coastal": true,
  "terrain": "flat | sloped | hilly | rocky",
  "target_date": "2025-12-01"
}
```

#### `FloorPlanRequest`
```json
{
  "buildable_zone": { ... },
  "user_requirements": { ... }
}
```

#### `RenderRequest`
```json
{
  "floor_plan": { ... },
  "site_schema": { ... },
  "buildable_zone": { ... },
  "user_requirements": { ... }
}
```

---

### Output Models

#### `SiteSchemaResponse` (Stage 1)

| Field | Type | Required |
|-------|------|----------|
| `plan_id` | string | yes |
| `plan_number` | string | no |
| `district` | enum (25 districts) | yes |
| `province` | string | no |
| `area_sqm` | float | yes |
| `road_access` | enum | yes |
| `is_coastal` | boolean | yes |
| `orientation_degrees` | float | yes |
| `frontage_m` | float | yes |
| `boundary_polygon` | [[x,y], ...] | yes |
| `page_dimensions` | {width, height} | yes |
| `scale` | string | no |
| `gps_lat` / `gps_lon` | float | no |
| `coordinate_n` / `coordinate_e` | float | no |
| `surveyor` / `licence_number` | string | no |

#### `BuildableZoneResponse` (Stage 2)

```json
{
  "buildable_polygon": [[x, y], ...],
  "max_footprint_sqm": 283.7,
  "max_total_built_sqm": 567.4,
  "recommended_floors": 2,
  "entrance_side": "south",
  "recommended_orientation_degrees": 180.0
}
```

#### `FloorPlanAlternative` (Stage 3, per alternative)

```json
{
  "layout_name": "conservative | balanced | creative",
  "rooms": [
    {
      "name": "master_bedroom",
      "x": 0.0, "y": 0.0,
      "width": 4.2, "height": 3.8,
      "area_sqm": 15.96
    }
  ],
  "total_area_sqm": 210.5,
  "quality_scores": {
    "space_utilisation": 0.87,
    "natural_light": 0.74,
    "adjacency": 0.81,
    "ventilation": 0.69,
    "overall": 0.78
  },
  "is_valid": true,
  "violations": []
}
```

#### `RenderResponse` (Stage 4)

```json
{
  "svg_path": "/tmp/r26_uploads/plan_abc123.svg",
  "pdf_path": "/tmp/r26_uploads/plan_abc123.pdf",
  "download_urls": {
    "svg": "/api/v1/download/plan_abc123.svg",
    "pdf": "/api/v1/download/plan_abc123.pdf"
  },
  "building_schema": { ... }
}
```

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GEMINI_API_KEY` | **Yes** | — | Google Gemini API key for Stage 3 LLM generation |
| `REDIS_URL` | Yes (Stage 3) | `redis://localhost:6379/0` | Celery broker and result backend |
| `SUPABASE_URL` | No | — | Supabase project URL for pgvector RAG store |
| `SUPABASE_KEY` | No | — | Supabase anon/service key |
| `SCHEMA_DIR` | No | `../shared/schemas` | Path to directory containing `site_schema.json` and `building_schema.json` |
| `C02_BASE_URL` | No | — | Component 02 base URL; when unset, Stage 4 skips the integration POST |
| `COMPONENT02_ENDPOINT` | No | — | Explicit C02 endpoint path used by the Stage 4 handoff |
| `TEMP_FILES_DIR` | No | — | Directory for temp file storage (uploads, SVG, PDF outputs) |
| `MAX_UPLOAD_SIZE_MB` | No | — | Rejects uploads larger than this |
| `MODEL_DIR` | No | `../Architecture/models` | Directory containing the Stage 1 CNN classifier |
| `CORPUS_DIR` | No | `../Architecture/knowledge_base/corpus` | Local RAG corpus ingested by `knowledge_base.ingest` |
| `CHROMA_HOST` | No | `localhost` | ChromaDB host for the local RAG vector store |
| `CHROMA_PORT` | No | `8000` | ChromaDB port |
| `GEMINI_FLOOR_PLAN_MODEL` | No | — | Overrides the Gemini model used for Stage 3 generation |
| `USE_VERTEX_AI` | No | `false` | Route Gemini calls through Vertex AI instead of the public API |
| `GOOGLE_CLOUD_PROJECT` | No | — | GCP project id, required when `USE_VERTEX_AI` is set |
| `GOOGLE_CLOUD_LOCATION` | No | — | GCP region, required when `USE_VERTEX_AI` is set |
| `VIDEO_RATE_LIMIT_HOURS` | No | — | Minimum hours between Stage 5 video generations |
| `LOG_LEVEL` | No | `INFO` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `FLAGS_enable_pir_api` | No | `0` | Set to `0` on Windows to suppress PaddleOCR PIR warnings |
| `FLAGS_use_mkldnn` | No | `0` | Set to `0` on Windows to disable MKL-DNN |
| `CUDA_VISIBLE_DEVICES` | No | `""` | Force CPU inference (set to empty string) |

**Minimal `.env` for local development:**
```env
GEMINI_API_KEY=your_key_here
REDIS_URL=redis://localhost:6379/0
SCHEMA_DIR=../shared/schemas
```

---

## Dependencies

Installed via `pip install -r requirements.txt`. Requires **Python 3.11**.

| Category | Package | Version | Purpose |
|----------|---------|---------|---------|
| Web framework | fastapi | 0.111.0 | REST API |
| | uvicorn[standard] | 0.30.1 | ASGI server |
| | python-multipart | 0.0.9 | File upload parsing |
| | pydantic | 2.10.6 | Request/response validation |
| OCR & Vision | easyocr | ≥1.7.1 | Text extraction from plan images |
| | opencv-python-headless | 4.10.0.84 | Boundary polygon detection |
| | PyMuPDF | 1.25.5 | PDF → PNG conversion |
| | Pillow | 11.0.0 | Image preprocessing |
| NLP & LLM | spacy | 3.8.14 | Custom cadastral NER model |
| | google-genai | 2.0.1 | Gemini API (migrated from google-generativeai) |
| | langchain | 0.3.25 | LLM orchestration utilities |
| | langchain-community | 0.3.25 | Community integrations |
| | sentence-transformers | 3.0.1 | RAG embedding (all-MiniLM-L6-v2) |
| Geometry | shapely | 2.0.7 | Polygon buffering for setback computation |
| | pyproj | 3.7.0 | SLD99 → WGS84 coordinate conversion |
| | jsonschema | 4.22.0 | JSON Schema validation |
| Rendering | svgwrite | 1.4.3 | SVG floor plan generation |
| | reportlab | 4.2.2 | PDF document rendering |
| Async | celery | 5.4.0 | Async task queue for Stage 3 |
| | redis | 5.0.6 | Celery broker/backend |
| Database | supabase | 2.15.2 | pgvector RAG client |
| | sqlalchemy | 2.0.30 | ORM |
| | psycopg2-binary | 2.9.10 | PostgreSQL adapter |
| ML | torch | 2.6.0 | EasyOCR inference backend |
| | torchvision | 0.21.0 | Image transforms |
| | scikit-learn | 1.5.2 | Evaluation metrics |
| | numpy | 2.3.5 | Numerical operations |
| Utilities | python-dotenv | 1.0.1 | `.env` loading |
| | httpx | 0.28.1 | Async HTTP (C02 integration POST) |

> **Note:** `paddlepaddle` is listed in requirements for reference but EasyOCR (PyTorch-based) is the active OCR engine — it resolves Windows PIR/OneDNN incompatibilities with numpy 2.x.

---

## JSON Schemas

Both schemas live in `shared/schemas/` (relative to the repo root). The service resolves this via `SCHEMA_DIR`. If the directory or file is missing, `SchemaAssembler` and `SchemaSerialiser` log a warning and skip validation rather than failing startup.

### `site_schema.json` — Stage 1 output contract

**Required fields:** `plan_id`, `district`, `area_sqm`, `road_access`, `is_coastal`, `orientation_degrees`, `frontage_m`, `boundary_polygon`, `page_dimensions`

**district enum (25 values):** Ampara, Anuradhapura, Badulla, Batticaloa, Colombo, Galle, Gampaha, Hambantota, Jaffna, Kalutara, Kandy, Kegalle, Kilinochchi, Kurunegala, Mannar, Matale, Matara, Monaragala, Mullaitivu, Nuwara Eliya, Polonnaruwa, Puttalam, Ratnapura, Trincomalee, Vavuniya

**road_access enum:** `national_road`, `provincial`, `local`, `lane`

### `building_schema.json` — Stage 4 output contract (→ C02)

**Required fields:** `footprint_sqm`, `perimeter`, `floors`, `floor_height`, `wall_height`, `excavation_depth`, `column_count`, `openings_sqm`, `internal_wall_length`, `finish_grade`, `roof_type`, `district`, `is_coastal`, `terrain`, `road_access`, `plot_area`, `rooms`, `bathroom_count`, `room_count`, `base_rate_date`, `target_date`

**finish_grade enum:** `economy`, `mid`, `luxury`  
**roof_type enum:** `flat`, `hip`, `gable`  
**terrain enum:** `flat`, `sloped`, `hilly`, `rocky`

---

## Running Locally

### Prerequisites

- Python 3.11
- Redis (required for Stage 3 — install via `brew install redis` on macOS or download from redis.io for Windows)
- Supabase project (optional — Stage 3 falls back to hardcoded design norms without it)

### 1. Install dependencies

```bash
cd Architecture
pip install -r requirements.txt
python -m spacy download en_core_web_sm
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env and fill in GEMINI_API_KEY at minimum
```

Or set `SCHEMA_DIR` explicitly if running from a different directory:

```bash
export SCHEMA_DIR=$(pwd)/../shared/schemas
```

### 3. Start Redis

```bash
# macOS / Linux
redis-server

# Windows (WSL or Docker)
docker run -p 6379:6379 redis:alpine
```

### 4. Start the API server

```bash
uvicorn main:app --reload --port 8001
```

API will be available at `http://localhost:8001`. Interactive docs at `http://localhost:8001/docs`.

### 5. Start the Celery worker (required for Stage 3)

In a separate terminal:

```bash
cd Architecture
celery -A tasks.celery_app worker --loglevel=info
```

### 6. (Optional) Seed the vector database

```bash
python seed_plans.py
# or
python embed_plans.py
```

---

## Running with Docker

The Dockerfile uses `Architecture/` as its build context with `WORKDIR /app`.

```bash
# Build the image
docker build -t c01-architecture .

# Run the API (requires Redis and env vars)
docker run \
  -p 8001:8001 \
  -e GEMINI_API_KEY=your_key \
  -e REDIS_URL=redis://host.docker.internal:6379/0 \
  c01-architecture
```

For a full stack including Redis and Celery, use the root `docker-compose.yml` in the repository.

---

## Testing

Tests are in `Architecture/tests/`. They must be run from the `Architecture/` directory so that `conftest.py` can add the correct path and all bare imports resolve.

```bash
cd Architecture

# Run all tests
pytest

# Run a specific file
pytest tests/test_buildable_zone.py

# Run a specific class or test
pytest tests/test_extraction.py::TestOCREngine
pytest -k "test_nbc_coastal"

# Verbose with stdout
pytest -v -s
```

### Test structure

| File | Covers |
|------|--------|
| `tests/test_extraction.py` | `OCREngine`, `CadastralClassifier`, `BoundaryDetector`, `NERParser`, `SchemaAssembler` |
| `tests/test_buildable_zone.py` | `NBCConstraintEngine`, `BuildableZoneCalculator`, `OrientationSolver` |
| `tests/test_generator.py` | Stage 3 RAG retrieval, LLM generation, validation, scoring |

### Fixtures (`tests/conftest.py`)

All tests share a canonical sample based on **Plan No. 2362, Ampara, 472.9 sqm, coastal**. The fixtures are:

- `sample_site_schema` — full Stage 1 output
- `sample_buildable_zone` — full Stage 2 output
- `sample_user_requirements` — standard user request
- `sample_floor_plan` — one complete floor plan alternative

Heavy ML dependencies (EasyOCR, SpaCy model, Supabase, Gemini) are stubbed with `unittest.mock.patch` — tests do not require any external services running.

---

## Key Design Decisions

### OCR: EasyOCR over PaddleOCR
EasyOCR is PyTorch-based and compatible with numpy 2.x. PaddleOCR has PIR API and MKL-DNN incompatibilities on Windows with Python 3.11+ that block startup without special flags.

### Normalised polygon coordinates
All boundary polygon coordinates are in [0, 1] relative to image dimensions. Real-world dimensions are derived from `area_sqm` at query time. This keeps Stage 1 independent of scan resolution.

### Shapely inward buffering for setbacks
NBC setbacks are applied as a negative buffer on the normalised polygon, then the result is scaled back to real square metres using the plot's `area_sqm`. This correctly handles non-rectangular plots.

### Lazy ML imports
PaddleOCR, SpaCy, ChromaDB, and Gemini imports are done inside endpoint handlers and Celery tasks — not at module level. This keeps startup time fast and test isolation clean (mocks only need to be applied inside the function scope).

### Three-temperature LLM generation
Conservative (T=0.4), Balanced (T=0.7), and Creative (T=1.0) Gemini calls run in parallel. This gives users a genuine choice between predictable layouts and more novel designs, all validated to the same NBC rules.

### Strip-packing layout solver
`solve_overlaps()` in `layout_solver.py` uses a strip-packing algorithm to eliminate room overlaps while keeping rooms within the buildable zone boundary. This corrects the most common failure mode of pure LLM spatial output.

### Fire-and-forget C02 handoff
Stage 4 flattens all pipeline outputs into a flat Building Schema and POSTs it to `${C02_BASE_URL}/estimate`. If C02 is unreachable or returns an error, it is logged and ignored — Stage 4 always returns a successful response to the caller.

### RAG fallback
If Supabase pgvector is unreachable, `RAGRetriever` returns three hardcoded Sri Lankan design norm strings. This keeps the pipeline runnable in dev environments without a database.

---

## MLOps & Model Utilities

| Script | Purpose |
|--------|---------|
| `train_ner.py` | Train the custom SpaCy NER model on annotated cadastral data |
| `convert_to_spacy.py` | Convert annotation files to SpaCy binary training format |
| `generate_synthetic.py` | Generate synthetic cadastral text for NER data augmentation |
| `review_annotations.py` | Visual tool to verify NER label boundaries |
| `batch_ocr.py` | Bulk OCR processing for a directory of plan images |
| `benchmark_models.py` | Evaluate OCR and NER accuracy against human-annotated baselines |
| `benchmark_results.csv` | Stored evaluation metrics (precision, recall, F1) |
| `seed_from_images.py` | Bootstrap vector DB by embedding plan images |
| `seed_plans.py` | Load sample plans into the Supabase pgvector collection |
| `embed_plans.py` | Full embedding pipeline for the knowledge base corpus |

The fine-tuned NER model is stored in `models/ner_cadastral/` with custom entity labels for Sri Lankan cadastral fields: `PLAN_NO`, `LICENCE`, `SURVEYOR`, `DISTRICT`, `AREA`, `SLD99_N`, `SLD99_E`, and others.

---

## Inter-Component Integration

| Component | Direction | Mechanism | When |
|-----------|-----------|-----------|------|
| **C02 (Cost Estimation)** | C01 → C02 | HTTP POST to `${C02_BASE_URL}/estimate` | End of Stage 4; fire-and-forget |
| **Gateway** | C01 ← Gateway | Reverse proxy routing to port 8001 | All inbound API requests in production |
| **Frontend** | C01 ← Frontend | Direct API calls or via Gateway | File upload, status polling, download |

The Building Schema posted to C02 contains all fields defined in `shared/schemas/building_schema.json`. C02 should not need to call any other C01 endpoint — the schema is designed to be self-contained for cost estimation.

---

## Logging

All log output is JSON-structured to stdout using `utils/logger.py`. Each entry includes:

```json
{
  "timestamp": "2025-01-01T12:00:00Z",
  "level": "INFO",
  "component": "C01",
  "module": "stage1_extraction.ocr_engine",
  "message": "OCR completed: 47 tokens extracted"
}
```

Use `get_logger(__name__)` from `utils.logger` in all modules — do not use `print` or `logging` directly.

---

# Component 02 — Cost Estimation Service

AI-driven construction cost estimation for Project R26-IT-117. Accepts a building schema produced by Component 01 and returns a fully priced cost report with uncertainty bounds, risk-adjusted contingency, and SHAP-based cost driver explanations.

---

## Architecture

The service is structured as a **4-layer sequential pipeline**:

```
Building Schema (JSON)
        │
        ▼
┌──────────────────────────────────────────────────┐
│  Layer 1 — BOQ Engine                            │
│  Derives structural, finishing & services        │
│  quantities from geometry and room counts        │
└──────────────────────┬───────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────┐
│  Layer 2 — Rate Engine                           │
│  Applies ICTAD unit rates, district multiplier,  │
│  and time-based price escalation                 │
└──────────────────────┬───────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────┐
│  Layer 3 — ML Prediction                         │
│  XGBoost Quantile (point + p5/p95 interval)      │
│  90% confidence interval via quantile regression │
│  SHAP explanations for top-5 cost drivers        │
└──────────────────────┬───────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────┐
│  Layer 4 — Risk Adjuster                         │
│  Risk scoring, contingency build-up,             │
│  and final Cost Report assembly                  │
└──────────────────────┴───────────────────────────┘
        │
        ▼
  Cost Report (JSON)
```

### Layer breakdown

| Layer | Module | Responsibility |
|-------|--------|----------------|
| 1 | `layers/layer1_boq/` | Structural, finishing, and services quantity take-off |
| 2 | `layers/layer2_rate_engine/` | ICTAD rate loading, district multiplier, escalation |
| 3 | `layers/layer3_ml_prediction/` | Feature engineering, XGBoost (point + quantile), SHAP |
| 4 | `layers/layer4_risk_adjuster/` | Risk scoring, contingency, report builder |

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/estimate` | Full 4-layer cost report |
| `POST` | `/boq` | Layer 1 BOQ quantities only |
| `GET` | `/rates` | ICTAD unit rate schedule (Layer 2) |
| `GET` | `/materials` | Material variants available per BOQ part (Layer 2) |
| `POST` | `/retrain` | Trigger model retraining *(admin only)* |
| `GET` | `/health` | Liveness check |

### Authentication

The `/retrain` endpoint requires an `X-Admin-Key` header matching the `ADMIN_API_KEY` environment variable.

---

## Request Schema (`BuildingSchema`)

| Field | Type | Description |
|-------|------|-------------|
| `footprint_sqm` | float | Ground-floor footprint (m²) |
| `perimeter` | float | External perimeter (m) |
| `floors` | int | Number of floors (1–10) |
| `floor_height` | float | Floor-to-floor height (m) |
| `finish_grade` | string | `economy` \| `mid` \| `luxury` |
| `roof_type` | string | `flat` \| `gable` \| `hip` \| `mansard` |
| `district` | string | Sri Lankan district name |
| `terrain` | string | `flat` \| `sloped` \| `hilly` \| `rocky` |
| `is_coastal` | bool | Coastal site flag (affects risk) |
| `road_access` | string | `paved` \| `gravel` \| `track` \| `none` |
| `rooms` | object | Room counts (bedrooms, bathrooms, etc.) |
| `base_rate_date` | string | ISO date for ICTAD base rates |
| `target_date` | string | ISO projection date (defaults to today) |

---

## ML Model

### Model Selection

Four models were benchmarked on 500 synthetic CIDA-calibrated records, using the
production 18-feature set, an 80/20 split (`random_state=42`). All were fitted on
`log1p(cost)`; every metric below is computed in rupee space on exponentiated predictions.

| Model | MAE (LKR) | MAPE (%) | R² | Prediction Interval |
|-------|-----------|----------|----|---------------------|
| Linear Regression | 1,518,072 | 12.81 | 0.908 | — |
| Random Forest | 1,595,124 | 13.75 | 0.893 | — |
| XGBoost (Point) | 1,742,957 | 14.55 | 0.881 | — |
| **XGBoost (Quantile)** | **1,956,021** | **16.56** | **0.832** | **51% (90% target)** |

**The comparison cannot discriminate model quality, and is not the basis for selection.**
Training labels are produced by executing Layers 1, 2 and 4 and multiplying by
lognormal(0, 0.15) noise. That noise alone imposes an irreducible MAPE floor of
`sigma*sqrt(2/pi)` = **11.97%** and an R² ceiling of **≈0.898**. The leading model sits
0.84 points above the floor and is statistically indistinguishable from the ceiling — the
surrogate task is saturated, and the four models differ only in how closely each fits a
near-log-linear deterministic generator.

XGBoost Quantile is deployed on **capability, not point accuracy**, on which it ranks last:

- the only candidate producing a **90% prediction interval natively**, without bootstrap
- the only candidate supporting **exact TreeSHAP** attribution per estimate
- **<1 ms inference** on CPU; ~2 MB of model JSON

It costs 3.75 points of MAPE relative to Linear Regression and buys per-estimate uncertainty
bounds and cost-driver explanations that the deterministic pipeline cannot produce.

**Open issue:** the 90% nominal interval achieves only 51% empirical coverage. The quantile
models over-fit the conditional quantiles of a near-deterministic function, so the interval
is too tight out of sample. Unresolved — see Known Limitations.


### Training Data

- 500 synthetic buildings, ICTAD/CIDA 2024-Q4 rates, 15% lognormal market noise
- 19 engineered features from building geometry, location, and finish grade
- All models trained on `log1p(cost)`; predictions exponentiated back to LKR

---

## Running Locally

### With Docker

```bash
docker build -t cost-estimation .
docker run -p 8000:8000 \
  -e ADMIN_API_KEY=your-key \
  cost-estimation
```

### Without Docker

```bash
cd cost-estimation
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Interactive docs available at `http://localhost:8000/docs`.

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ADMIN_API_KEY` | Yes (for retrain) | Key for the `X-Admin-Key` header |
| `LOG_LEVEL` | No | Logging level (default: `INFO`) |

---

## Project Structure

```
cost-estimation/
├── main.py                        # FastAPI app + pipeline orchestration
├── requirements.txt
├── Dockerfile
├── README.md                      # Component-level documentation
├── data/                          # ICTAD rates, material catalog, scraped prices
├── models/                        # Trained model artefacts (gitignored)
├── scripts/                       # Training and data-preparation utilities
├── tests/
└── layers/
    ├── layer1_boq/
    │   ├── boq_engine.py          # Orchestrates quantity take-off
    │   ├── structural_boq.py
    │   ├── finishing_boq.py
    │   └── services_boq.py
    ├── layer2_rate_engine/
    │   ├── rate_engine.py         # Orchestrates pricing
    │   ├── ictad_loader.py
    │   ├── material_catalog.py
    │   └── price_escalation.py
    ├── layer3_ml_prediction/
    │   ├── ensemble.py            # XGBoost point + quantile predictor
    │   ├── xgboost_model.py
    │   ├── feature_engineer.py
    │   └── shap_explainer.py
    └── layer4_risk_adjuster/
        ├── risk_scorer.py
        ├── contingency.py
        └── report_builder.py
```

---

## Known Limitations / TODO

- `/retrain` endpoint is a stub — actual retraining pipeline (PostgreSQL pull + script run) is not yet wired
- XGBoost Quantile coverage is 51% vs the 90% target — the quantile models over-fit on 400 training rows; candidate fixes are conformal calibration, K-fold interval estimation, or reduced depth/estimators
- Dataset is synthetic; model should be retrained once real project records are available

---

# Component 03 — Project Management & Timeline Prediction

**Service Port:** `8000`
**Framework:** FastAPI + Uvicorn
**Entry point:** `app.main:app`
**API Version:** `1.0.0`

---

## Overview

Component 03 takes the Cost Estimation output from Component 02 and produces a
full construction schedule. It predicts **phase-wise durations** with Random
Forest and XGBoost, predicts **total project duration** with a PyTorch LSTM
over the phase sequence, then derives the critical path, milestones, task
dependencies, basic resource allocation, and a Gantt-ready task list.

It also emits a *planned schedule* payload shaped for Component 04, which is
what links the planning half of the system to the monitoring half.

The service deliberately does **not** do cost estimation, site monitoring,
delay prediction, or progress tracking — those belong to Components 02 and 04.

---

## Pipeline Architecture

```
[Cost Estimation JSON from C02]
        │
        ▼
┌─────────────────────────────────────────────────────────┐
│  ml_service / random_forest_service                     │
│  Random Forest + XGBoost → per-phase durations (weeks)  │
└─────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────┐
│  lstm_service                                           │
│  PyTorch LSTM over the phase sequence → total duration  │
└─────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────┐
│  cpm_service          → critical path, float, milestones│
│  gantt_service        → Gantt rows and dependencies     │
│  resource_service     → basic resource allocation       │
└─────────────────────────────────────────────────────────┘
        │
        ├──────────────► timeline_service → prediction response
        │
        └──────────────► performance_format_service
                         → planned schedule payload for C04
```

---

## Directory Structure

```
timeline/
├── Dockerfile                     # EXPOSE 8000, runs uvicorn app.main:app
├── requirements.txt
├── README.md
├── sample_request.json            # Example C02-shaped request body
├── app/
│   ├── main.py                    # FastAPI app, CORS, router registration
│   ├── config.py                  # Settings dataclass (DATABASE_URL, origins)
│   ├── database.py
│   ├── models/
│   │   └── schemas.py             # Pydantic request/response models
│   ├── routes/
│   │   └── timeline_routes.py     # /api/timeline/predict, /performance-format
│   ├── services/
│   │   ├── timeline_service.py    # Orchestrates the full prediction
│   │   ├── ml_service.py          # XGBoost phase-duration inference
│   │   ├── random_forest_service.py
│   │   ├── lstm_service.py        # PyTorch LSTM total-duration inference
│   │   ├── cpm_service.py         # Critical path method
│   │   ├── gantt_service.py       # Gantt chart assembly
│   │   ├── resource_service.py    # Resource allocation
│   │   └── performance_format_service.py  # C04 handoff payload
│   ├── training/
│   │   ├── generate_synthetic_dataset.py
│   │   ├── train_random_forest.py
│   │   ├── train_xgboost.py
│   │   ├── train_lstm_pytorch.py
│   │   ├── train_lstm_model.py
│   │   └── evaluate_models.py
│   └── utils/
│       └── response_utils.py
├── data/
│   ├── residential_timeline_dataset.csv   # 1,000 rows — primary training set
│   ├── construction_projects.csv          # 500 rows
│   └── generate_dataset.py
├── models/                        # Trained artefacts (committed)
│   ├── timeline_random_forest_model.pkl
│   ├── timeline_xgboost_model.pkl
│   ├── timeline_lstm_pytorch.pt
│   ├── lstm_x_scaler.pkl
│   └── lstm_y_scaler.pkl
└── output/                        # Evaluation plots and metrics
    ├── model_evaluation_results.csv
    ├── correlation_heatmap.png
    ├── phase_distributions.png
    ├── avg_phase_duration.png
    ├── boxplots.png
    └── lstm_training_plot.png
```

> **Legacy code —** `timeline/main.py` together with `timeline/pipeline/` and
> `timeline/output/*.py` is an earlier, separate implementation of this service.
> Nothing runs it: the Dockerfile launches `app.main:app`, and `app/` imports
> nothing from `pipeline/`. It is reachable only from
> `timeline/tests/test_schedule.py`. The extra artefacts in `models/`
> (`*_weeks_model.pkl`, `scaler.pkl`, `encoders.pkl`, `features.pkl`,
> `schedule_xgboost.json`, `lstm_total_model.h5`) belong to that older path,
> as do the root-level `train.py` and `train_lstm.py`. Pending removal.

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Health check |
| `POST` | `/api/timeline/predict` | Full timeline prediction and project management output |
| `POST` | `/api/timeline/performance-format` | Planned schedule payload for Component 04 |

Interactive docs at `http://localhost:8000/docs`. A ready-made request body is
committed at `timeline/sample_request.json`.

---

## Machine Learning Models

| Model | Predicts | Artefact |
|-------|----------|----------|
| Random Forest | Phase durations + total duration | `timeline_random_forest_model.pkl` |
| XGBoost | Phase durations + total duration | `timeline_xgboost_model.pkl` |
| PyTorch LSTM | Total duration from the phase sequence | `timeline_lstm_pytorch.pt` (+ `lstm_x_scaler.pkl`, `lstm_y_scaler.pkl`) |

### Evaluation results

From `output/model_evaluation_results.csv`:

| Model | MAE | RMSE | R² | MAPE (%) |
|-------|-----|------|----|----------|
| Random Forest | 1.92 | 3.06 | 0.828 | 6.97 |
| **XGBoost** | **1.43** | **2.28** | **0.875** | **5.48** |
| PyTorch LSTM | 14.48 | 18.73 | 0.978 | 5.94 |

XGBoost is the strongest on the phase-duration task. The LSTM's MAE and RMSE
are on a different scale because it predicts total project duration rather than
individual phases — compare it on R² and MAPE, not on absolute error.

---

## Training

All training scripts live in `app/training/` and are run from the `timeline/`
directory. Datasets are committed, so training is reproducible from a fresh
clone.

```bash
cd timeline
python -m app.training.generate_synthetic_dataset   # regenerate the dataset (optional)
python -m app.training.train_random_forest
python -m app.training.train_xgboost
python -m app.training.train_lstm_pytorch
python -m app.training.evaluate_models              # writes output/model_evaluation_results.csv
```

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | No | `sqlite:///./timeline_predictions.db` | Persistence for stored predictions |

No API keys or external service credentials are needed — Component 03 runs
entirely offline against its committed models.

---

## Running Locally

```bash
cd timeline
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## Running with Docker

```bash
docker build -t r26-timeline ./timeline
docker run -p 8000:8000 r26-timeline
```

## Testing

```bash
pytest timeline/tests -v
```

Note the current test file targets the legacy `pipeline/` implementation, not
`app/`; the live service has no test coverage yet.

---

## Known Limitations / TODO

- Two parallel implementations coexist — see the *Legacy code* note above.
- The live `app/` service has no tests.
- The service is not yet added to `docker-compose.yml`.
- Port `8000` is the FastAPI/uvicorn default and is easy to collide with; C01
  uses 8001, C02 8002, C04 5004.


---

# Component 04 — Construction Performance Monitoring and Delay Prediction

## Overview

Component 04 of the R26-IT-117 Construction Planner AI system. Monitors construction
project schedules by calculating Schedule Performance Index (SPI) from progress updates,
predicts delay risk using a trained XGBoost model, retrieves similar historical cases
from a FAISS vector index, and generates corrective action recommendations via Google Gemini.

---

## Tech Stack

| Layer            | Technology                               |
|------------------|------------------------------------------|
| Web framework    | Flask 3 + Flask-CORS                     |
| Database         | PostgreSQL 15 via SQLAlchemy             |
| ML model         | XGBoost (classifier + regressor)         |
| Embeddings       | Sentence Transformers (all-MiniLM-L6-v2) |
| Vector search    | FAISS (Flat L2 index, 192 vectors)       |
| LLM              | Google Gemini 2.0 Flash                  |
| Weather data     | External Weather API (integration planned)|
| Containerisation | Docker + Docker Compose                  |
| Language         | Python 3.11                              |

---

## Project Structure

```
performance/
├── main.py                    # Flask app — endpoints, validation, orchestration
├── train.py                   # Trains the delay classifier + regressor
├── requirements.txt
├── Dockerfile
├── .env                       # Not committed — see Environment Variables
├── database/
│   └── db.py                  # ORM models, schema creation, migrations, seed data
├── pipeline/
│   ├── spi_calculator.py      # SPI calculation and alert level logic
│   ├── feature_engineer.py    # Feature mapping, encoding, matrix building
│   └── delay_model.py         # XGBoost model loading and prediction
├── rag/
│   ├── embedder.py            # SentenceTransformer, story generation from CSV
│   ├── faiss_index.py         # FAISS index build, load, search
│   └── rag_pipeline.py        # Case retrieval and field extraction
├── llm/
│   └── gemini_client.py       # Gemini prompt building, response parsing, fallback
├── monitoring/
│   └── dashboard_feed.py      # Project dashboard aggregation queries
├── weather/
│   └── weather_client.py      # Weather API client for location-based risk
├── timeline_source/
│   ├── base.py                # Provider interface
│   ├── factory.py             # Selects provider from TIMELINE_SOURCE
│   ├── local_provider.py      # Reads a schedule from disk
│   └── remote_provider.py     # Calls the Component 03 timeline service
├── data/
│   ├── delay_data.csv         # 192 historical delay cases
│   └── rag_cases/             # 192 generated story .txt files for FAISS indexing
├── models/                    # Generated — not committed to git
│   ├── xgboost_classifier.json
│   ├── xgboost_regressor.json
│   ├── label_encoders.pkl
│   ├── faiss_rag.index
│   └── faiss_rag_meta.json
└── tests/
    ├── test_model.py
    ├── test_spi.py
    ├── test_rag.py
    ├── test_feature_engineer.py
    ├── test_frontend_safety.py
    ├── test_phase_status.py
    ├── test_schedule_validation.py
    ├── test_timeline_source.py
    └── test_weather.py
```

---

## Environment Variables

Create a `.env` file inside `performance/`:

```env
# ── Core ──────────────────────────────────────────────────────────────────────
DATABASE_URL=postgresql://postgres:password@localhost:5432/r26_db
GEMINI_API_KEY=your_gemini_api_key_here
FLASK_ENV=development
PORT=5004

# ── Delay case data (RAG corpus source) ───────────────────────────────────────
DELAY_CASES_CSV_PATH=data/delay_data.csv

# ── Component 03 timeline source ──────────────────────────────────────────────
# TIMELINE_SOURCE selects the provider in timeline_source/factory.py:
#   local  → read a schedule from disk
#   remote → call the Component 03 service at TIMELINE_SERVICE_BASE_URL
TIMELINE_SOURCE=local
TIMELINE_SERVICE_BASE_URL=http://localhost:8000

# ── Weather API ───────────────────────────────────────────────────────────────
WEATHER_API_KEY=your_weather_api_key_here
WEATHER_API_BASE_URL=
WEATHER_API_COUNTRY_CODE=LK
WEATHER_API_TIMEOUT_SECONDS=10

# ── Outbound notifications ────────────────────────────────────────────────────
NOTIFY_TIMEOUT_SECONDS=10
```

---

## How to Run

**With Docker Compose (recommended)**
```bash
docker-compose up --build
```

**Directly**
```bash
cd performance
pip install -r requirements.txt
python main.py
```

**Tests**
```bash
pytest tests/
```

Service runs on `http://localhost:5004`.

---

## API Endpoints

### GET /health
Returns live database connection status.

### POST /schedule
Creates a project and saves its phase schedule baseline. Entry point for all new projects.

**Request body**
```json
{
  "project": {
    "name": "Jaffna Coastal Residence",
    "district": "Jaffna",
    "province": "Northern Province",
    "floors": 2,
    "building_type": "Residential"
  },
  "phases": [
    {
      "phase_group": "Foundations",
      "sub_phase": "Foundation work",
      "planned_start": "2026-01-01",
      "planned_end": "2026-02-15",
      "planned_duration_days": 45,
      "sequence": 1
    }
  ]
}
```

---

### POST /progress/spi
Records a progress update and calculates SPI. Creates an alert if WARNING or CRITICAL.

**Request body**
```json
{
  "phase_id": 1,
  "actual_percent": 45.0,
  "entered_by": "PM-Thulasika"
}
```

**Alert level thresholds**

| SPI value   | Alert level |
|-------------|-------------|
| > 0.85      | NORMAL      |
| 0.70 – 0.85 | WARNING     |
| < 0.70      | CRITICAL    |

> When response returns `requires_prediction_step: true`, proceed to `/progress/predict`.

---

### POST /progress/predict
Runs the full delay prediction pipeline. Only callable after a WARNING or CRITICAL SPI result.

**Request body**
```json
{
  "spi_id": 1,
  "phase_id": 1,
  "delay_category": "Labour",
  "labour_availability": "Low",
  "material_supply": "Yes",
  "weather_severity": "Minor"
}
```

**Valid values**

| Field                 | Accepted values |
|-----------------------|-----------------|
| `delay_category`      | `Labour`, `Material Supply & Quality`, `Environmental & Site`, `Financial & Funding`, `Design & Technical`, `Land & Legal`, `Owner / Social / Behavioural` |
| `labour_availability` | `Very Low`, `Low`, `Medium`, `Good`, `Full` |
| `material_supply`     | `Yes`, `No` |
| `weather_severity`    | `No disruption`, `Minor`, `Moderate`, `Severe` |

---

### GET /project/\<id\>/dashboard
Returns full project status — phases, latest SPI, prediction, recommendation, and alerts.

### GET /project/\<id\>/alerts
Returns active alerts. Add `?active_only=false` to include resolved alerts.

---

### Additional routes

These are implemented in `main.py` alongside the endpoints documented above.

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Service banner / root check |
| `GET` | `/projects` | List all projects |
| `POST` | `/project` | Create a project |
| `POST` | `/project/\<id\>/phases` | Attach or replace a project's phase list |
| `PATCH` | `/project/\<id\>/location` | Update a project's location (drives the weather lookup) |
| `GET` | `/project/\<id\>/weather` | Current weather for the project location |
| `POST` | `/predict` | Delay prediction without the SPI wrapper |
| `POST` | `/progress` | Record raw progress data |

---

## End-to-End Flow

```
1. POST /schedule              → save project and phases
2. POST /progress/spi          → calculate SPI and alert level
3. POST /progress/predict      → run ML prediction + RAG + Gemini
4. GET  /project/{id}/dashboard → view full project status
5. GET  /project/{id}/alerts    → view active alerts
```

---

## ML Pipeline

**Training data:** 192 historical Sri Lankan coastal residential construction delay cases

**Input features:** `phase_group`, `sub_phase`, `district`, `province`, `floors`,
`delay_category`, `labour_availability`, `material_supply`, `weather_severity`, `cumulative_delay`

**Outputs:**
- `delay_risk` — `HIGH`, `MEDIUM`, or `LOW`
- `estimated_delay_days` — integer ≥ 0

### Training

`models/` is generated and gitignored, so a fresh clone has no artefacts and
the prediction endpoints will fail until you train:

```bash
cd performance
pip install -r requirements.txt
python train.py
```

That writes `xgboost_classifier.json`, `xgboost_regressor.json` and
`label_encoders.pkl` into `models/`. The classifier is tuned with
`BayesSearchCV` over 8 iterations and trained on SMOTE-balanced data; the
regressor uses fixed hyperparameters. `train.py` imports `FEATURES` from
`pipeline/delay_model.py`, so the training and serving feature order cannot
drift apart.

The CSV is resolved in the same order `rag/embedder.py` uses:
`DELAY_CASES_CSV_PATH`, then `performance/data/delay_data.csv`, then
`research/datasets/delay-cases/delay_data.csv`.

Then build the RAG index, which is also generated:

```bash
python -c "from rag.embedder import generate_rag_documents; generate_rag_documents()"
python -c "from rag.faiss_index import build_index; build_index()"
```

Reference results from a clean run on the committed 192-case dataset:
classifier accuracy 0.897, weighted F1 0.897, 5-fold CV F1 0.943 (±0.008);
regressor MAE 29.6 days, RMSE 58.1 days.

---

## RAG Pipeline

Retrieves top 3 similar historical delay cases to ground LLM recommendations.
Uses SentenceTransformer embeddings and FAISS Flat L2 index over 192 case documents.

---

## LLM Integration

Gemini 2.0 Flash generates a plain-language explanation and up to 5 corrective actions
based on project context and retrieved historical cases. Falls back to generic
recommendations if the API is unavailable.

---

## Weather API Integration

External weather data integration is planned for a future release. The intent is to
automatically populate `weather_severity` from a live weather API based on the
project district, removing the need for manual input by site supervisors.

---

## Known Limitations

- No authentication (planned for gateway layer)
- No duplicate submission detection
- No correction or delete endpoints
- No email or SMS alert delivery
- ML model is static — no retraining pipeline on live data
- Weather severity currently entered manually — external API integration planned
