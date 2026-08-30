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
│  Applies ICTAD unit rates and time-based         │
│  price escalation                                │
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
| 2 | `layers/layer2_rate_engine/` | ICTAD rate loading, price escalation |
| 3 | `layers/layer3_ml_prediction/` | Feature engineering, XGBoost (point + quantile), SHAP |
| 4 | `layers/layer4_risk_adjuster/` | Risk scoring, contingency, report builder |

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/estimate` | Full 4-layer cost report |
| `POST` | `/boq` | Layer 1 BOQ quantities only |
| `GET` | `/rates` | ICTAD unit rate schedule |
| `GET` | `/materials` | Material variants per BOQ part with current rates |
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
| `terrain` | string | `flat` \| `sloped` \| `hilly` \| `rocky` |
| `is_coastal` | bool | Coastal site flag (affects risk) |
| `road_access` | string | `paved` \| `gravel` \| `track` \| `none` |
| `rooms` | object | Room counts (bedrooms, bathrooms, etc.) |
| `materials` | object | Optional material per BOQ part, e.g. `{"door_count": "plywood_flush"}` |
| `base_rate_date` | string | ISO date for ICTAD base rates |
| `target_date` | string | ISO projection date (defaults to today) |

---

## Material Variants & Price Scraping

Five BOQ parts support 2–5 material variants each (`door_count`, `window_count`,
`roof_area_sqm`, `floor_tile_sqm`, `ceiling_sqm`), defined in
`data/material_catalog/material_catalog.csv`. Selecting a material in the
request prices that part from the catalog. Parts left unselected fall back to
the **finish grade's default material**; an explicit selection always wins.
Every `/estimate` response includes a `material_options.alternatives` block
comparing the line cost under each variant.

| Part | economy | mid | luxury |
|------|---------|-----|--------|
| `door_count` | plywood_flush | solid_timber_teak | solid_timber_teak |
| `window_count` | steel_framed | aluminium_sliding | timber_casement |
| `roof_area_sqm` | fiber_cement_sheet | concrete_tile | clay_tile |
| `floor_tile_sqm` | cement_render_floor | ceramic_tile_300 | porcelain_tile |
| `ceiling_sqm` | pvc_panel | pvc_panel | gypsum_board |

Market prices are refreshed by a **scheduled scraper job** — never in the
request path:

```bash
python scripts/scrape_stockpile.py --dry-run           # inspect without writing
python scripts/scrape_stockpile.py                     # update the price overlay
python scripts/scrape_stockpile.py --show-unmatched    # list unclassified products
```

`--show-unmatched` lists products no classification rule caught (tagged
`accessory` or `no_rule`) — review it after each run to grow the rule set.

The scraper (stockpile.lk, server-rendered Magento) classifies products into
catalog keys, normalises units, rejects outliers, and writes the median supply
price per material to `data/scraped_prices/current_prices.csv`. Medians that
deviate >50% from the seed rate go to `review_queue.csv` for a human instead.
All raw samples are appended to `price_history.csv` — a growing time series
intended as training data for the CCPI escalation model. Overlay rows older
than 45 days are ignored, so a broken scraper degrades gracefully to seed rates.

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

### Interval calibration

Raw quantile regression was badly miscalibrated — a 90% nominal band achieved 51% empirical
coverage. **Conformalized Quantile Regression** now corrects this: the quantile models are
fitted on a proper-training subset and a held-out calibration subset (35% of training data)
supplies an additive offset in log space, giving a distribution-free finite-sample coverage
guarantee. Measured on the held-out test set:

| Interval | Nominal | Empirical | Mean width |
|---|---:|---:|---:|
| Two-sided (displayed) | 50% | **51.0%** | 25.2% |
| Two-sided | 90% | **94.0%** | 67.4% |
| One-sided budget | 90% | **90.0%** | — |

A calibrated 90% band is ~67% wide and unusable as a headline, so `/estimate` returns three
figures instead of one:

- `lower_bound_lkr` / `upper_bound_lkr` — the **likely range**, a 50% band, ~25% wide
- `interval_90_lkr` — the wider 90% band, retained for analysis
- `budget_lkr` — one-sided 90% upper bound: *90% of comparable projects come in at or below
  this*, which is the figure a client budgets against

`interval_is_calibrated` reports whether conformal offsets were available. **The offsets are
only valid for the models they were computed with — retraining without recalibrating silently
voids the guarantee**, so `scripts/train_model.py` always does both.


### Training Data

- 500 synthetic buildings, ICTAD/CIDA 2024-Q4 rates, 15% lognormal market noise
- 18 engineered features from building geometry, site conditions, and finish grade
- All models trained on `log1p(cost)`; predictions exponentiated back to LKR

---

## Running Locally

### With Docker

```bash
docker build -t cost-estimation .
docker run -p 8002:8002 \
  -e ADMIN_API_KEY=your-key \
  cost-estimation
```

### Without Docker

```bash
cd cost-estimation
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8002
```

Interactive docs available at `http://localhost:8002/docs`.

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
- **Estimates under-price by ~2.3x against published 2025/26 per-ft2 market bands; 0% of mid
  and luxury estimates fall inside their published band.** The ICTAD rate CSV values are
  indicative rather than sourced from a real CIDA bulletin, the BOQ omits scope (staircase,
  septic/water tank, boundary wall, external works), and the finish-grade factors are far too
  compressed (25% economy-to-luxury spread vs ~3x in the published bands). This is the single
  most important open defect
- Interval calibration is resolved (conformal); the *width* is still dominated by the assumed
  contractor variance sigma = 0.15, which is a modelling choice and has not been measured
- Dataset is synthetic; model should be retrained once real project records are available
