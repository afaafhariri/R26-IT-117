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
    └── test_feature_engineer.py
```

---

## Environment Variables

Create a `.env` file inside `performance/`:

```env
DATABASE_URL=postgresql://postgres:password@localhost:5432/r26_db
GEMINI_API_KEY=your_gemini_api_key_here
FLASK_ENV=development
PORT=5004
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
