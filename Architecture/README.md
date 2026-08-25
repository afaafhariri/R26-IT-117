# Component 01 — Architectural Planning API

**Project:** R26-IT-117 — AI-Driven Construction Planner for Sri Lankan Residential Construction  
**Branch:** `dev/shazni`  
**Service Port:** `8001`  
**API Version:** `v0.1.0`

---

## Overview

Component 01 is a FastAPI microservice that turns a Sri Lankan cadastral plan upload (PDF or image) into a fully validated Building Schema ready for downstream cost estimation (Component 02). It implements a **4-stage sequential pipeline** — Extraction → Buildable Zone → Floor Plan Generation → Rendering — each exposed as an independent REST endpoint under `/api/v1`.

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
```

---

## Directory Structure

```
Architecture/
├── main.py                         # FastAPI app, all route definitions
├── app.py                          # Deprecated 1-line placeholder (do not edit)
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

### `GET /api/v1/floor-plan-status/{task_id}` — Stage 3 (poll)

Polls the Celery result backend for the task status.

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

**Query param:** `dir` (optional) — subdirectory within `UPLOAD_DIR`.

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
| `UPLOAD_DIR` | No | `/tmp/r26_uploads` | Directory for temp file storage (uploads, SVG, PDF outputs) |
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
