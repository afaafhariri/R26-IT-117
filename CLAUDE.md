# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Layout — what exists vs. what is scaffolding

This is a multi-component final-year research project (`R26-IT-117`, "AI-Driven Construction Planner" for Sri Lankan residential construction). On `main`, **only Component 01 (`Architecture/`) contains real code** — the other top-level directories (`cost-estimation/`, `perfomance/`, `timeline/`, `frontend/`, `gateway/`, `shared/`, `infra/`, root `docker-compose.yml`, root `.env.example`) are mostly empty placeholder files committed to reserve structure. Component work for C02/C03/C04 happens on per-developer branches:

- `dev/shazni`, `dev/hanfi`, `dev/hariri`, `dev/thulasika` — each owner's component lives on their branch
- `dev/hanfi` was merged in PR #2 ("Timeline / Component 04"); inspect that branch when working on C04
- `main` is intentionally minimal — do not assume code exists in `timeline/app.py` etc. on `main`; check `git log --all -- <path>` before editing

Note `perfomance/` is misspelled in the repo (do not "fix" it without a wider rename — it is referenced from `gateway/routes/perfomance.py` etc.).

## Component 01 — Architectural Planning API (`Architecture/`)

FastAPI service implementing a 4-stage pipeline that turns a Sri Lankan cadastral plan upload into a validated Building Schema for downstream components.

### Pipeline (each stage = one HTTP endpoint, all under `/api/v1`)

1. **`POST /extract`** — Stage 1 (sync). PDF/image upload → PyMuPDF page render → PaddleOCR → CNN cadastral classifier → OpenCV boundary polygon detection → spaCy NER → `SchemaAssembler` produces a `site_schema` validated against `shared/schemas/site_schema.json`.
2. **`POST /buildable-zone`** — Stage 2 (sync). Applies `NBCConstraintEngine` (NBC Sri Lanka setbacks + BCR per district + coastal flag) and computes the buildable polygon, footprint, recommended floors, and orientation.
3. **`POST /generate-floor-plan` + `GET /floor-plan-status/{task_id}`** — Stage 3 (async via Celery). RAG retrieval over ChromaDB (collection `sl_residential_plans`, embedder `all-MiniLM-L6-v2`) → prompt builder → **3 parallel Gemini calls at temperatures 0.4 / 0.7 / 1.0** (labelled conservative / balanced / creative) → geometric validator → scorer. Returns `task_id`; poll status endpoint.
4. **`POST /render`** — Stage 4 (sync). SVG render → PDF render → `SchemaSerialiser` validates `building_schema.json` and **fire-and-forget POSTs to `${C02_BASE_URL}/estimate`** (failure is non-blocking — must never raise from here).

### Entry point and import quirks

- Entry: `Architecture/main.py` (`uvicorn main:app --port 8001`). `Architecture/app.py` is a 1-line placeholder; do not put the app there.
- Imports are bare top-level (`from stages.stage1_extraction.ocr_engine import ...`, `from utils.logger import get_logger`) — they only resolve when CWD is `Architecture/` or `Architecture/` is on `sys.path`. `Architecture/conftest.py` injects this for pytest. The Dockerfile sets `WORKDIR /app` with `Architecture/` as the build context.
- Heavy ML imports (PaddleOCR, torch, spaCy, ChromaDB, sentence-transformers, google-generativeai) are deliberately **lazy** — done inside endpoint handlers and Celery tasks, not at module top. Preserve this when editing; eager imports break startup time and test isolation.
- Logger (`utils/logger.py`) emits JSON to stdout with `"component": "C01"` — use `get_logger(<module>)` rather than `print` or stdlib logging directly.

### JSON schemas (data contracts)

`SCHEMA_DIR` (default `shared/schemas`) holds `site_schema.json` (loaded by `SchemaAssembler`) and `building_schema.json` (loaded by `SchemaSerialiser`) — both exist on `dev/shazni`. If the directory is missing, both classes log a warning and skip validation rather than failing. File names are matched exactly. To run the API or tests against these schemas locally, set `SCHEMA_DIR=$(pwd)/../shared/schemas` from `Architecture/`.

### External services

- **Redis** (`REDIS_URL`, default `redis://localhost:6379/0`) — Celery broker AND backend.
- **ChromaDB** (`CHROMA_HOST`/`CHROMA_PORT`, default `localhost:8000`) — RAG store. If unreachable, `RAGRetriever` falls back to hardcoded design norms (3 strings) — do not remove this fallback; it keeps the pipeline runnable in dev without ChromaDB.
- **Gemini** (`GEMINI_API_KEY`, model `gemini-1.5-flash`) — required for Stage 3.
- **C02** (`C02_BASE_URL`) — optional; when unset, Stage 4 logs and skips the integration POST.

## Common commands (run from `Architecture/`)

```bash
# Install (Python 3.11)
pip install -r requirements.txt
python -m spacy download en_core_web_sm

# Run the API
uvicorn main:app --reload --port 8001

# Run the Celery worker (Stage 3 async generation requires this)
celery -A tasks.celery_app worker --loglevel=info

# Tests — must be run from Architecture/ so conftest.py puts it on sys.path
pytest                                            # all tests
pytest tests/test_buildable_zone.py               # one file
pytest tests/test_extraction.py::TestOCREngine    # one class
pytest -k "test_nbc_coastal"                      # by name
pytest -v -s                                      # verbose + show stdout

# Build the C01 image (build context is Architecture/)
docker build -t c01-architecture .
```

Tests heavily use `unittest.mock.patch` to stub PaddleOCR, spaCy, ChromaDB, and Gemini — they do not need those services running. Fixtures in `tests/conftest.py` (`sample_site_schema`, `sample_buildable_zone`, `sample_user_requirements`, `sample_floor_plan`) model the canonical "Plan No. 2362, Ampara, 472.9 sqm coastal" example used throughout the codebase — reuse them rather than inventing new sample data.

## Working across branches

Code review and ownership: `.github/CODEOWNERS` lists `@afaafhariri` as owner. Each component-owner branch (`dev/<name>`) has its own merge cycle into `main` — when a task touches multiple components, expect to switch branches rather than find everything on one branch.
