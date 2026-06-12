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
| `GET` | `/rates/{district}` | ICTAD rates for a Sri Lankan district |
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

Four models were benchmarked on 500 synthetic CIDA-calibrated records:

| Model | MAE (LKR) | MAPE (%) | R² | Prediction Interval |
|-------|-----------|----------|----|---------------------|
| Linear Regression | 1,763,255 | 12.38 | −2.98 | — |
| Random Forest | 1,993,548 | 13.72 | −2.98 | — |
| XGBoost (Point) | 1,954,597 | 13.87 | −2.98 | — |
| **XGBoost (Quantile)** | **2,667,688** | **16.81** | **0.76** | **52% (90% target)** |

XGBoost Quantile was selected for production because it:
- Explains **76% of cost variance** (R² = 0.76)
- Provides **native 90% confidence intervals** without bootstrap overhead
- Produces **SHAP attributions** per prediction (footprint, district, finish grade, etc.)
- Runs at **<1 ms inference** on CPU; model file ~2 MB


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
└── layers/
    ├── layer1_boq/
    │   ├── boq_engine.py          # Orchestrates quantity take-off
    │   ├── structural_boq.py
    │   ├── finishing_boq.py
    │   └── services_boq.py
    ├── layer2_rate_engine/
    │   ├── rate_engine.py         # Orchestrates pricing
    │   ├── ictad_loader.py
    │   ├── district_multiplier.py
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
- XGBoost Quantile coverage is 52% vs the 90% target; quantile alpha needs tuning
- Dataset is synthetic; model should be retrained once real project records are available
