# Changelog — Component 02, Cost Estimation

Changes to the service, its training data and its trained models, newest first. Every entry
that changes Layer 1, 2 or 4 also changes the training data, because the synthetic records are
priced by those layers; such entries retrain the models and record the new results.

Reference building used below: 150 m² footprint, 50 m perimeter, 2 floors (300 m²), Colombo,
mid grade, 36 m² of openings, 60 m of internal walls per floor, priced for 1 October 2026.

---

## 2026-10-15 — Remove unused dependencies; keep the local environment out of the image

### Removed

- **Five packages C02 never imported:** `paddlepaddle`, `paddleocr`, `psycopg2-binary`,
  `sqlalchemy` and `geoalchemy2`. They arrived on 29 April 2026 (`30e63c9`) under the heading
  "OCR (shared with Component 01)" when `requirements.txt` was restructured; TensorFlow and
  Keras from the same list were removed on 4 May (`84bb576`), but these were left behind.
  `paddlepaddle` was skipped on macOS, so the full OCR stack was installed only inside the
  Linux image.
- **Dockerfile system packages they needed:** `libpq-dev` (psycopg2) and `libglib2.0-0`,
  `libsm6`, `libxext6`, `libxrender-dev` (OCR). `libgomp1` (XGBoost) and `wget` (health check)
  stay.

### Added

- **`.dockerignore`.** The Dockerfile's `COPY . .` copied the local `.venv/` (841 MB of
  platform-specific files, unusable inside the Linux image) into every build, along with
  caches, tests and `.env`. Dependencies are installed in the image from `requirements.txt`,
  so nothing at runtime used them. The root `.gitignore` ignores every `.dockerignore`, so an
  exception (`!cost-estimation/.dockerignore`) shares this one.

### Verified

A fresh Python 3.12 environment built only from the new `requirements.txt` passes all 129
tests, and `/estimate` returns the same reference-building total (LKR 22,973,008) with
calibrated intervals. `docker build` now sends a 6.8 MB build context instead of 852 MB and
produces a 1.56 GB image (Docker 29.8, linux/arm64). The container runs as `appuser`, passes
its health check, contains no `.venv/` or `tests/`, loads all seven model files and returns
the same total.

---

## 2026-10-15 — Price reinforcement steel and internal wall finishes; retrain; track models

### Fixed

- **Reinforcement steel was never priced.** Layer 1 estimates steel at 110 kg per m³ of
  concrete and the rate schedule has a steel rate (LKR 260/kg at the base date), but the rate
  engine priced only the `structural`, `finishing` and `services` sections, and the steel
  estimate lives in the BOQ `summary`. It is now added as a line item, `steel_kg_estimate`.
  (`layers/layer2_rate_engine/rate_engine.py`)
- **Internal walls were neither plastered nor painted.** Plaster covered both faces of the
  external walls only; paint covered one face of the external walls plus the ceilings. Plaster
  now covers both faces of the external walls and of the internal partitions; paint covers
  every plastered face plus the ceilings. The internal wall length uses the same default as
  the structural bill, so plastered partitions match the blockwork.
  (`layers/layer1_boq/finishing_boq.py`)
- The planner labels the new line "Reinforcement steel" (`planner-ui/src/components/ui.tsx`).

### Effect on the reference building

| | Before | After |
|---|---:|---:|
| Reinforcement steel | not priced | 6,194 kg, LKR 1.92 M |
| Wall plaster | 600 m², LKR 0.61 M | 1,320 m², LKR 1.34 M |
| Paint | 600 m², LKR 0.25 M | 1,620 m², LKR 0.68 M |
| Direct cost | LKR 13.63 M | LKR 16.71 M |
| Total | LKR 18.74 M | LKR 22.97 M |
| Cost per m² | LKR 62,483 | LKR 76,577 |
| ML point estimate | LKR 22.58 M | LKR 25.59 M |
| Likely range (50%) | LKR 18.42 M – 25.56 M | LKR 21.12 M – 30.78 M |
| Budget figure | LKR 28.40 M | LKR 35.91 M |

Median generated cost per ft² by grade (500 records): economy 5,229 → 6,570, mid 6,413 → 7,799,
luxury 7,769 → 9,404.

### Retrained

```bash
cd cost-estimation
python tests/generate_dataset.py   # 500 records, seed 42 -> research/datasets/cost-records/cost.csv
python scripts/train_model.py      # 80/20 split (random_state=42); 35% of training rows calibrate
```

Held-out test set (100 records):

| Metric | Before | After |
|---|---:|---:|
| Point model R² | 0.876 | 0.889 |
| Point model MAPE | 14.8% | 14.4% |
| 50% band coverage (width) | 50% (26.8%) | 46% (26.0%) |
| 90% band coverage (width) | 88% (72.2%) | 90% (69.1%) |
| Budget figure, share at or below | 90% | 94% |
| R² ceiling set by the label noise | 0.896 | 0.900 |
| Median latency, full estimate with SHAP | 38.0 ms | 37.2 ms |

The MAPE floor set by the label noise is unchanged at 11.97%. Four-model comparison
(`scripts/model_comparison.py`): Linear Regression MAPE 12.73% / R² 0.910, Random Forest
14.02% / 0.898, XGBoost point 14.42% / 0.889, XGBoost quantile 17.02% / 0.832 with 53% raw
coverage at a nominal 90%.

### Models tracked in git again

`cost-estimation/models/*.json` is no longer ignored. All seven files are loaded by the
service: the point model, the quantile models at 0.05, 0.25, 0.75, 0.90 and 0.95, and
`conformal_offsets.json` (about 6.4 MB in total). The empty `.gitkeep` is removed.

### Tests

124 → 129. New: steel is priced at quantity × rate; direct cost equals the sum of all lines;
plaster covers both faces of external and internal walls; paint covers plastered walls and
ceilings; partitions add plaster. The four quantity and steel tests fail on the previous code.

---

## 2026-10-01 — Fix the price drift between the models and the service (`c606a37`)

### Fixed

- **The models and the service priced buildings differently.** Training records were priced
  with whatever material overlay and dates applied when the dataset was generated, while the
  service escalates rates, applies material selections and scraped prices at request time, so
  the ML figures drifted away from the rate-engine total.
- The generator now prices every record at grade-default materials, seed catalogue rates and
  the 2024-10-01 base date, with the scraped-price overlay off
  (`MaterialCatalog(use_overlay=False)`).
- The service scales the ML outputs by a price factor κ = direct cost of the request ÷ direct
  cost of the same building priced the way the training data were (`main._price_factor`).
  The ensemble and the SHAP explainer accept `price_factor`, and the report records it in
  `model_metadata.price_factor`. A uniform factor leaves interval coverage unchanged.

### Retrained

Point model R² 0.876, MAPE 14.8%; calibrated coverage 50% / 88% / 90% for the 50% band, the
90% band and the budget figure. Tests: 124.

### Repository

The models, `research/datasets/cost-records/cost.csv` and `research/reports/` stopped being
tracked (tracking of the models was restored on 2026-10-15).
