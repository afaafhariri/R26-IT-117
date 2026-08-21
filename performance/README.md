# C04 — Construction Performance Monitoring and Delay Prediction

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
| ML model         | XGBoost (classifier + regressor), CPU-only build (`xgboost-cpu`) |
| Embeddings       | Sentence Transformers (all-MiniLM-L6-v2) |
| Vector search    | FAISS (Flat L2 index, 192 vectors)       |
| LLM              | Google Gemini (`gemini-flash-latest`)    |
| Weather data     | OpenWeatherMap "Current Weather" API, live per-district lookup with graceful fallback |
| Containerisation | Docker + Docker Compose                  |
| Language         | Python 3.11                              |

---

## Project Structure

```
performance/
├── main.py                    # Flask app — endpoints, validation, orchestration
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
│   └── weather_client.py      # Live weather lookup, condition→severity mapping, fallback
├── timeline_source/
│   ├── base.py                 # TimelineProvider interface (see Architecture below)
│   ├── local_provider.py       # LocalMockTimelineProvider — default, backed by Performance's own tables
│   ├── remote_provider.py      # RemoteTimelineProvider — scaffolded, not implemented yet
│   └── factory.py              # Picks the active provider via TIMELINE_SOURCE
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
    └── test_weather.py
```

### Architecture note — Timeline data

Performance does not own project/phase schedule data long-term. All reads of that
data go through the `TimelineProvider` interface (`timeline_source/`), never direct
SQL. `TIMELINE_SOURCE=local` (default) backs it with Performance's own Postgres
tables as a development convenience; `TIMELINE_SOURCE=remote` will call the real
Timeline component's API once it exists (not implemented yet — see
`timeline_source/remote_provider.py`). `POST /schedule` is a temporary dev-only
seeding endpoint for the local provider and is disabled when `TIMELINE_SOURCE=remote`.

---

## Environment Variables

Create a `.env` file inside `performance/`:

```env
DATABASE_URL=postgresql://postgres:password@localhost:5432/r26_db
GEMINI_API_KEY=your_gemini_api_key_here
FLASK_ENV=development
PORT=5004

# Downstream component notification (sent on HIGH delay risk)
C02_URL=http://cost-estimation:5002
C03_URL=http://timeline:5003
NOTIFY_TIMEOUT_SECONDS=5

# Weather integration (weather/weather_client.py) — optional. If unset or the
# live call fails, weather calls fall back to "No disruption" gracefully.
WEATHER_API_KEY=your_openweathermap_api_key_here
WEATHER_API_BASE_URL=https://api.openweathermap.org/data/2.5/weather
WEATHER_API_COUNTRY_CODE=LK
WEATHER_API_TIMEOUT_SECONDS=5

# Timeline data source (timeline_source/) — see Architecture note above.
# "local" (default) = Performance's own tables, for development only.
# "remote" = real Timeline component API (not implemented yet).
TIMELINE_SOURCE=local
TIMELINE_SERVICE_BASE_URL=http://timeline:5003
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

### GET /projects
Lists all projects (name, district, province, floors, building type). Read-only,
sourced via `TimelineProvider`. Feeds a project-name dropdown for clients instead of
requiring a raw numeric `project_id`.

### GET /project/\<id\>/weather
Live weather preview for a project's district — returns the same server-side weather
resolution `/progress/predict` uses internally, so a client can see what will feed the
prediction before submitting. Never hard-fails: on a weather-provider error this still
returns `200` with `"success": false` and a fallback severity.

### POST /schedule
Creates a project and saves its phase schedule baseline. Entry point for all new projects.
Temporary/dev-only — see the Architecture note above; disabled when `TIMELINE_SOURCE=remote`.

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
| `weather_severity`    | `No disruption`, `Minor`, `Moderate`, `Severe` (optional — see below) |

> `weather_severity` is optional. If omitted, it is resolved automatically server-side
> from live weather for the project's district (see Weather API Integration below). If
> supplied, it's used as an explicit manual override and no live call is made.

---

### GET /project/\<id\>/dashboard
Returns full project status — phases, latest SPI, prediction, recommendation, and alerts.

### GET /project/\<id\>/alerts
Returns active alerts. Add `?active_only=false` to include resolved alerts.

---

### Deprecated endpoints

`POST /project`, `POST /project/<id>/phases`, `POST /progress`, and `POST /predict` are
legacy routes from an earlier API shape. They now return `410 Gone` with a message
pointing to their replacement (`POST /schedule`, `POST /progress/spi` +
`POST /progress/predict`) — kept only so old clients get a clear error instead of a 404.

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

---

## RAG Pipeline

Retrieves top 3 similar historical delay cases to ground LLM recommendations.
Uses SentenceTransformer embeddings and FAISS Flat L2 index over 192 case documents.

---

## LLM Integration

Gemini (`gemini-flash-latest`) generates a plain-language explanation and up to 5
corrective actions based on project context, the delay-assessment inputs (main delay
category, labour/material availability), resolved weather, and retrieved historical
cases. Falls back to generic recommendations if the API is unavailable (invalid key,
rate limit, quota, network error, etc.) — `/progress/predict` never hard-fails just
because Gemini is unreachable.

---

## Weather API Integration

Implemented (`weather/weather_client.py`), using OpenWeatherMap's "Current Weather
Data" endpoint. `GET /project/<id>/weather` previews live weather for a project's
district; `POST /progress/predict` resolves `weather_severity` automatically the same
way server-side unless a manual override is supplied in the request body. Weather
condition, rainfall, and wind are mapped onto the model's existing 4-label severity
scale (`No disruption` / `Minor` / `Moderate` / `Severe`). If `WEATHER_API_KEY` is
unset, or the live call fails or times out, this falls back to `"No disruption"`
rather than failing the prediction request.

---

## Known Limitations

- No authentication (planned for gateway layer)
- No duplicate submission detection
- No correction or delete endpoints
- No email or SMS alert delivery
- ML model is static — no retraining pipeline on live data
- `TIMELINE_SOURCE=remote` (the real Timeline component integration) is scaffolded but
  not implemented yet — every method raises `NotImplementedError` until Timeline's API
  exists; `TIMELINE_SOURCE=local` (default) is the only usable mode today
