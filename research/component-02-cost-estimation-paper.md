# Component 02 — Cost Estimation Service
## Research material for IEEE submission

**Project:** R26-IT-117 — AI-Driven Construction Planner
**Component:** 02 — Cost Estimation
**Code audited at:** commit `ab4ea19`, branch `dev/hariri`, 30 August 2026
**Codebase:** `cost-estimation/` — 4,448 lines of Python, 108/108 unit tests passing (10.2 s)

This document records (a) what the component actually does, at the level of detail an IEEE
paper needs, (b) the measured results and a correction to the results currently published in
the repository README, and (c) an audit of which supplied sources were genuinely used, with an
IEEE reference list restricted to those.

---

## 0. Status of the evaluation code — corrections applied 30 Aug 2026

Three defects in the *evaluation and reporting* layer were found and fixed. None touched the
service, the trained models, or any estimate the API returns. They are recorded here because
the first one changes what the paper may claim.

### 0.1 The R² metric was scored against log-space predictions — FIXED

`scripts/model_comparison.py::evaluate_all` computed, for Linear Regression, Random Forest and
XGBoost, `r2_score(y_test, predictions_log)` — rupee-space ground truth against log-rupee
predictions. The result was dominated by the unit mismatch, which is why all three reported an
identical −3.5432. Only XGBoost Quantile was scored in rupee space (0.807), so the table was
not like-for-like. All four are now scored on exponentiated predictions.

**The published conclusion inverted.** XGBoost Quantile has the *lowest* R² and the *highest*
MAE and MAPE of the four; it ranks last on every accuracy metric. The selection argument that
rested on "explains 81% of cost variance while the others are worse than a mean baseline" does
not hold and has been removed from both READMEs.

The replacement argument is stronger and is developed in §5.4: the surrogate task is saturated,
so *no* model comparison on this dataset can discriminate quality, and selection must rest on
capability — native prediction intervals and exact TreeSHAP.

Also fixed in the same pass: the comparison trained on 22 columns while production inference
uses 18. It now uses `FeatureEngineer.feature_names()`, so the benchmark measures the deployed
configuration.

### 0.2 The generated report contained hardcoded, unmeasured prose — FIXED

`generate_report()` interpolated the metrics table into an otherwise static narrative asserting
a "65% XGBoost + 35% MLP ensemble", a "~2% accuracy gain", "R² = 0.759" and "MAE 2.67M". None
were computed; no MLP exists in the codebase. `scripts/show_results.py` printed the same stale
figures, contradicting `metrics.csv`. Both now derive every figure at run time. The dead
`StandardScaler`, the `train_neural_network()` stub and the "5 models" docstring claim were
removed; `plot_comparison.py` had a latent `ValueError` in its R² normalisation, also fixed.

### 0.3 The dataset is circular — NOT a defect, but it bounds every claim

`tests/generate_dataset.py` produces labels by running Layers 1 → 2 → 4 (the deterministic rule
engine) and multiplying the grand total by lognormal(0, σ = 0.15). Layer 3 is then trained to
predict that. **The ML model is a surrogate of the rule engine plus injected noise, not a model
of observed construction cost.**

This is legitimate and publishable provided it is framed correctly: it verifies that the learned
surrogate reproduces the deterministic estimator faithfully enough to supply uncertainty bounds
and SHAP attribution at sub-millisecond cost. It says nothing about real-world cost accuracy,
and the paper must not claim otherwise. §5.4 quantifies exactly what it does and does not show;
§6.3 gives the external validation that partially bounds it.

---

## 1. Contribution statement

Component 02 accepts a machine-readable Building Schema (produced by Component 01 from
architectural drawings) and returns a fully priced, risk-adjusted, explainable cost report.
The contributions defensible from the code as built are:

1. **An end-to-end automated quantity-take-off → pricing → risk → report pipeline** for Sri
   Lankan residential construction, requiring no quantity surveyor in the loop, executing in
   under one second.
2. **A material-variant pricing layer** — 22 variants across 5 BOQ parts — that returns, with
   every estimate, the cost of the building under each alternative material, enabling
   value-engineering at estimate time rather than post hoc.
3. **A staleness-gated live price overlay** fed by a scheduled retail-price scraper, with
   outlier rejection and a deviation-bounded human review queue, so that market prices refresh
   the estimate while a broken or anomalous scrape can never silently corrupt it.
4. **Per-estimate uncertainty and explanation** — a 90 % nominal prediction interval from
   quantile regression and top-5 SHAP cost drivers rendered in plain English.
5. **A structured downstream contract** exporting labour-day and structural-complexity
   aggregates to the scheduling (C03) and delay-prediction (C04) components.

Framing: this is an **early-stage / pre-bid** estimator. That is the regime where estimate
uncertainty is highest and where the literature identifies the greatest need [7], [8], [10].

---

## 2. System architecture

Four sequential layers behind a FastAPI service (`main.py`).

```
Building Schema (JSON, from C01)
   │
   ├─► Layer 1  BOQ Engine          quantity take-off: structural, finishing, services
   ├─► Layer 2  Rate Engine         CIDA/ICTAD unit rates × escalation × material variants
   ├─► Layer 3  ML Prediction       XGBoost point + p5/p95 interval, TreeSHAP attribution
   └─► Layer 4  Risk Adjuster       risk premia, contingency build-up, report assembly
   │
   ▼
Cost Report (JSON) ──► C03 scheduling ──► C04 delay prediction
```

**Important architectural fact for the paper.** The headline `summary.total_lkr` is produced
by Layer 4's deterministic contingency build-up, **not** by the ML model. The ML point
estimate is reported alongside it as `summary.ml_point_estimate_lkr`, and the ML p5/p95 models
supply the displayed interval. Layer 3 is an explanatory and uncertainty-quantification layer
over a deterministic estimator, not the estimator itself. Describing it otherwise would
misrepresent the system.

### API surface

| Method | Path | Function |
|---|---|---|
| POST | `/estimate` | Full four-layer cost report |
| POST | `/boq` | Layer 1 quantities only |
| GET | `/rates` | CIDA/ICTAD unit rate schedule |
| GET | `/materials` | Material variants per BOQ part with current rates |
| POST | `/retrain` | Retraining trigger (admin, `X-Admin-Key`) — **stub, not implemented** |
| GET | `/health` | Liveness |

---

## 3. Method

Notation: `P` external perimeter (m); `A_f` ground-floor footprint (m²); `N` storeys; `h_f`
floor-to-floor height (m); `h_w` wall height (m); `d_exc` excavation depth (m); `A_op` total
opening area (m²); `L_int` internal wall length (m); `n_c` column count.

### 3.1 Layer 1 — Bill of Quantities

**Structural** (`structural_boq.py`). Column count is derived when not supplied:
`n_c = max(4, ⌊P/4⌋)`.

```
V_exc   = P · d_exc · 0.6                          excavation
V_bl    = P · 0.6 · 0.05                           blinding concrete, C10
V_fc    = P · 0.6 · 0.45                           foundation concrete, C25
V_col   = n_c · (0.23)² · h_f · N                  RC columns, C30
V_slab  = A_f · 0.125 · N                          RC suspended slab, C25
V_ext   = max(0, P·h_w·N − A_op) · 0.23            225 mm external brickwork
V_int   = L_int · h_w · 0.115 · N                  115 mm internal blockwork
A_roof  = 1.30 · A_f                               roof area (pitch allowance)
```

Reinforcement is an indicative aggregate at 110 kg per m³ of total concrete:
`W_steel = 110 · (V_bl + V_fc + V_col + V_slab)`.

**Finishing** (`finishing_boq.py`). Base quantities at mid grade, scaled by a grade factor
γ ∈ {economy, mid, luxury}:

```
A_tile    = 0.90 · A_f · N · γ_tile
A_plaster = 2 · (P · h_w · N) · γ_plaster          both faces
A_ceiling = A_f · N · γ_ceiling
n_door    = max(1, round((n_rooms + n_bath + 1) · γ_door))
n_window  = max(2, round(2 · n_rooms · γ_window))
A_paint   = (P·h_w·N + A_f·N) · γ_paint
```

Grade factors (economy / mid / luxury): tile 0.85 / 1.00 / 1.10; plaster 1.00 / 1.00 / 1.05;
ceiling 0.80 / 1.00 / 1.20; doors 0.90 / 1.00 / 1.15; windows 0.85 / 1.00 / 1.20; paint
1.00 / 1.00 / 1.05. Unknown grades fall back to mid with a warning.

**Services** (`services_boq.py`). Electrical points from a per-room-type lookup
(living 8, master bedroom 6, bedroom 4, kitchen 8, bathroom 3, dining 4, study 4, garage 3,
store 2, balcony 2; unknown types default to 4), plus a fixed 6 for consumer unit,
distribution board and earth continuity:

```
E = Σ_r e_r · n_r + 6
```

Plumbing: 4 fixtures per bathroom (WC pan, washbasin, shower/bath, floor trap), plus kitchen
sink and waste trap per kitchen, plus 2 outdoor hose bibs.

### 3.2 Layer 2 — Rate Engine

**Rate source** (`ictad_loader.py`). A 17-item schedule keyed by BOQ item, resolved in
priority order: PostgreSQL → CSV (`data/ictad_rates/ictad_rates_2024_Q4.csv`) → hardcoded
fallback. *The PostgreSQL path raises `NotImplementedError`; in practice the CSV is always
used.* Rates are indicative 2024-Q4 CIDA/ICTAD values.

**Price escalation** (`price_escalation.py`). A linear monthly model:

```
Δm    = 12(y − y₀) + (m − m₀) + (d − d₀)/30
f     = 1 + r_m · Δm,        r_m = 0.008  (≈ 9.6 % p.a.)
R'    = R · f
```

*This is a placeholder.* The module's own TODO specifies replacement by a CIDA
Construction-Cost-Price-Index time-series model. See Section 6.1.

**Material variants** (`material_catalog.py`). 22 variants over 5 parts — `door_count` (5),
`window_count` (4), `roof_area_sqm` (4), `floor_tile_sqm` (5), `ceiling_sqm` (4). Effective
installed rate per (part *p*, material *m*):

```
              ⎧ s_pm + i_pm   if a scraped overlay row exists and
R_pm      =   ⎨                  (today − t_pm) ≤ 45 days
              ⎩ R̂_pm         otherwise (seed catalog rate)
```

where `s_pm` is the scraped median supply price, `i_pm` the seed installation cost, `R̂_pm`
the seed installed rate. The 45-day staleness gate guarantees graceful degradation to seed
rates if the scraper stops. Parts not explicitly selected in the request take the finish
grade's default material; an explicit selection always wins.

**Direct cost:**
```
C_direct = Σ_j Q_j · R_j · f
```

Every response also carries `material_alternatives`: for each part present in the BOQ, the
line cost under *every* variant, so the caller sees the price of each substitution.

**Price scraper** (`scripts/scrape_stockpile.py`, 380 lines, offline batch job — never on the
request path). Per category page of a server-rendered Magento catalogue (stockpile.lk):

1. Fetch all products in one request; 2.5 s inter-request delay, identifying User-Agent.
2. Classify product names to (part, material) by regex; an accessory/spares skip-list is
   applied first.
3. Normalise to catalogue units where the listing unit is known
   (ft² → m²: × 10.7639; 2′×2′ ceiling tile → m²: ÷ 0.3716). Where the unit is unknown the
   sample is recorded in history only and never reaches the overlay.
4. Reject outliers outside [0.25, 4.0] × group median; require n ≥ 3 surviving samples.
5. Gate on deviation from the seed supply rate: accepted to the overlay iff
   `|median − seed| / seed ≤ 0.50`, otherwise routed to `review_queue.csv` for a human.
6. All raw samples append to `price_history.csv` — a growing time series intended as training
   data for the CCPI escalation model.

Current state: 101 historical samples, 5 active overlay rows.

### 3.3 Layer 3 — ML prediction and explanation

**Features** (`feature_engineer.py`). x ∈ ℝ¹⁸, in four groups:

- *BOQ (8):* concrete_m3, steel_kg, brickwork_m3, floor_area_sqm, wall_plaster_sqm,
  door_count, window_count, bathroom_count
- *Ratio (4):* concrete_per_sqm, steel_to_concrete_ratio, opening_to_wall_ratio,
  perimeter_to_area_ratio
- *Location (3):* is_coastal (binary), terrain_encoded, road_access_encoded
- *Specification (3):* finish_grade_encoded, roof_type_encoded, floors

Categorical variables use ordinal integer maps: terrain {flat 0, sloped 1, hilly 2, rocky 3},
road access {paved 0, gravel 1, track 2, none 3}, roof {flat 0, gable 1, hip 2, mansard 3},
finish grade {economy 0, mid 1, luxury 2}. Non-finite values are replaced with 0.

**Models** (`xgboost_model.py`). Three XGBoost regressors on log-transformed cost
`z = log(1 + y)`:

- point: `objective = reg:squarederror`
- lower: `objective = reg:quantileerror`, α = 0.05
- upper: `objective = reg:quantileerror`, α = 0.95

Shared hyperparameters: n_estimators 500, max_depth 6, learning_rate 0.05, reg_alpha 0.1,
reg_lambda 1.0, subsample 0.8, colsample_bytree 0.8, random_state 42. *These are fixed
constants; no hyperparameter search was performed.*

Inference: `ŷ = exp(f(x)) − 1`; interval `[exp(f_.05(x)) − 1, exp(f_.95(x)) − 1]`.

**Explanation** (`shap_explainer.py`). Exact TreeSHAP on the point model. SHAP values φᵢ are
computed in log-cost space; conversion to a rupee impact uses the first-order (delta-method)
approximation, since d/dz·exp(z) = exp(z):

```
Impact_i ≈ φ_i · exp(f(x))
```

The top-5 features by |Impact| are returned with a human-readable label and a direction
(increases / decreases). **State the first-order nature of this conversion explicitly in the
paper** — it is exact only in the limit of small φ.

### 3.4 Layer 4 — Risk and contingency

**Risk scoring** (`risk_scorer.py`). Additive premia:

| Factor | Premium | Trigger |
|---|---:|---|
| Coastal site | +5 % | `is_coastal` |
| Multi-storey | +7 % | floors > 1 |
| Constrained plot | +5 % | plot area < 200 m² |
| Luxury finish | +10 % | grade = luxury |

`ρ = Σ premia`, maximum 27 %. Each applied factor is returned with a plain-language
justification. *These coefficients are engineering judgement; they are not calibrated against
data.* See Section 6.1.

**Contingency build-up** (`contingency.py`). Risk applies to direct cost; six on-costs then
compound sequentially on the running subtotal:

```
S₀ = C_direct · (1 + ρ)
S_k = S_{k−1} · (1 + r_k),   r = ⟨0.030, 0.035, 0.010, 0.015, 0.120, 0.050⟩
```
(site establishment, supervision, insurance, bonds & permits, profit & overhead, design
contingency)

```
C_total = C_direct · (1 + ρ) · Π_k (1 + r_k) = C_direct · (1 + ρ) · 1.285205
```

i.e. a fixed **+28.52 %** over the risk-adjusted subtotal. Note this is *compounding*, not
additive; the arithmetic sum of the six rates is 25.5 %.

**Downstream feed** (`report_builder.py`):

```
D_labour   = 10·V_concrete + 8·V_brickwork + 0.5·A_floor        (labour-days)
κ_struct   = min(1, (V_col + V_slab) / (V_col + V_slab + V_fc + 0.001))
```

plus trade-value breakdown (structural / finishing / services), floor area, storeys, and
district/province forwarded from the C01 schema for C03 and C04.

---

## 4. Experimental setup

| Item | Value |
|---|---|
| Dataset | 500 synthetic records, `research/datasets/cost-records/cost.csv` (500 × 27) |
| Generation | Layers 1→2→4 executed on randomised schemas; label = grand total × lognormal(0, 0.15) |
| Sampling | footprint ~ lognormal(ln 120, 0.4) clipped [50, 350] m²; storeys {1,2,3,4} p = .60/.28/.09/.03; grade {econ, mid, lux} p = .25/.55/.20; coastal p = .37; terrain p = .55/.20/.17/.08; road access p = .60/.25/.10/.05; plot ~ lognormal(ln 400, 0.6) clipped [80, 2000] m² |
| Seed | 42 (dataset generation and train/test split) |
| Split | 80 / 20 hold-out, `random_state = 42`. **No cross-validation.** |
| Target | `grand_total_lkr`, trained on log1p |
| Metrics | MAE, RMSE, MAPE, MdAPE, R², 90 % PI coverage, training time |
| Environment | Python 3.12, xgboost 2.1.4, scikit-learn 1.6.1, shap 0.46.0 |

Note the feature-set discrepancy: `model_comparison.py` trains on **22** columns (all numeric
columns except targets, adding footprint_sqm, perimeter, plot_area, room_count), while
production inference uses the **18**-feature set. Re-running the comparison on the production
18 gives MAPE 12.81 / 13.75 / 14.55 / 16.56 and corrected R² 0.908 / 0.893 / 0.881 / 0.832,
with 51 % PI coverage — same ordering, so the conclusion is unaffected, but **the paper should
report the 18-feature run** for consistency with the deployed model.

---

## 5. Results

### 5.1 Model comparison

Production 18-feature set, 500 records, 400/100 split, seed 42, all metrics in rupee space on
exponentiated predictions:

| Model | MAE (LKR) | RMSE (LKR) | MAPE (%) | MdAPE (%) | R² | 90 % PI coverage | Train (s) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Linear Regression | 1,518,072 | 2,008,375 | 12.81 | 10.71 | **0.908** | — | 0.002 |
| Random Forest | 1,595,124 | 2,170,364 | 13.75 | 12.60 | 0.893 | — | 0.068 |
| XGBoost (point) | 1,742,957 | 2,290,167 | 14.55 | 13.10 | 0.881 | — | 0.432 |
| XGBoost (Quantile) | 1,956,021 | 2,720,857 | 16.56 | 13.87 | 0.832 | **51.0 %** | 0.873 |

### 5.2 The comparison is saturated and cannot rank model quality

The labels are a deterministic function of the features multiplied by i.i.d. lognormal(0, σ)
noise with σ = 0.15. Two limits follow directly.

**MAPE floor.** For a multiplicative perturbation ε ~ lognormal(0, σ), the expected absolute
relative deviation of the best possible predictor is, to first order,

```
MAPE_min = σ · √(2/π) = 0.15 × 0.7979 = 11.97 %
```

**R² ceiling.** With y = y_true · ε and ε independent of the features,
E[y²] = E[y_true²]·e^{2σ²}, and the optimal predictor E[y|x] = y_true·e^{σ²/2} leaves an
irreducible residual variance E[y_true²](e^{σ²} − 1)e^{σ²}. Estimated on the dataset:

```
R²_max = 1 − 4.779×10¹² / 4.670×10¹³ = 0.8977      (rupee space)
       = 1 − 0.0225 / 0.2088          = 0.8923      (log space)
```

Measured: the best model reaches **12.81 % MAPE against an 11.97 % floor** (0.84 points above)
and **R² 0.908 against a 0.898 ceiling** — statistically indistinguishable, since the ceiling
is a population quantity while R² is measured on 100 test records.

**The leading model is already at the limit of what any estimator can achieve on these labels.**
Fitting a linear model to the noise-free `direct_cost_lkr` in log space gives **R² = 0.9933**,
confirming why: the rule engine is near-multiplicative (grade factors × escalation × (1+ρ) ×
1.2852), so under `log1p` it is very nearly *additive*, and a linear model is close to the
correct functional form by construction.

The four models therefore differ only in how closely each happens to fit a near-log-linear
deterministic generator. **No conclusion about relative model quality for real construction
cost data may be drawn from this table, and none is drawn.** The comparison must be re-run once
real project records are available.

### 5.3 Basis for deploying XGBoost Quantile

Given §5.2, selection rests on capability, not accuracy — on which it ranks last:

- the only candidate emitting a prediction interval **natively**, without bootstrap (which would
  cost 5–10× the training time for the other three)
- the only candidate supporting **exact TreeSHAP**, giving per-estimate cost-driver attribution
- < 1 ms CPU inference; ~2 MB of model JSON across the three model files

It costs **3.75 percentage points of MAPE** relative to Linear Regression and buys per-estimate
uncertainty bounds and explanations that the deterministic pipeline cannot produce. State this
trade explicitly; it is the honest and defensible argument.

*(Linear Regression is inherently interpretable via its coefficients, so the SHAP advantage is
weaker against that baseline than against the tree models. The interval advantage is not.)*

### 5.4 Open calibration failure

The 90 % nominal interval achieves **51 % empirical coverage**. The quantile models (500 trees,
depth 6, 400 training rows) over-fit the conditional quantiles of a near-deterministic function,
producing intervals that are too tight out of sample. This is unresolved and is reported as a
limitation, not smoothed over. Candidate remedies: conformal calibration on a held-out split,
K-fold interval estimation after Rasila et al. [4], or reduced depth/estimator count.

### 5.5 Functional verification

108 unit tests pass across four suites: `test_boq.py` (formula-level assertions on every
structural and finishing quantity, grade monotonicity, zero-input degeneracy),
`test_rate_engine.py` (escalation arithmetic, rate loading, fallbacks), `test_materials.py`
(2–5 variants per part, cheapest-first ordering, fresh-overlay application, staleness
rejection), `test_ensemble.py` (18-feature contract, interval ordering, save/load round-trip,
SHAP output shape and validity).

---

## 6. Limitations and future work

### 6.1 Stated honestly — these belong in the paper

| Limitation | Evidence in code | Supporting citation |
|---|---|---|
| **Dataset is synthetic and circular.** Model learns the rule engine, not observed cost. | `tests/generate_dataset.py` | Salleh et al. via [4]: fragmented, incomplete cost data limits ML training |
| **90 % PI achieves 51–52 % coverage.** Uncalibrated. | measured | Rasila et al. [4] treat interval tightness *and* validity as a selection criterion; their K-fold CI (model R8) is a candidate fix |
| **Escalation is a flat 0.8 %/month national linear factor.** No CIDA index, no regional differentiation. | `price_escalation.py` TODO | Nissanka & Wijesinghe [3] show ANOVA-significant provincial price divergence (bricks F = 557.9, p ≈ 10⁻⁷⁹; sand F = 143.9, p ≈ 10⁻⁵¹) — a single national index is demonstrably insufficient |
| **No regional/district pricing.** District and province are forwarded to C03/C04 but never priced against. | `report_builder.py` states this explicitly | [3] |
| **Risk premia are uncalibrated judgement** (5/7/5/10 %). | `risk_scorer.py` | — |
| **BOQ norms are fixed constants** (110 kg/m³ steel, 0.23 m wall, 0.125 m slab, 1.30 roof factor, 10/8/0.5 labour-day norms), unvalidated against site data. | Layer 1 | Jayathilaka et al. [2] rank "incorrect norms" (M28) a common material-overrun cause at 25 % frequency |
| **Terrain is an ML feature but carries no risk premium**, despite hilly-site foundation costs reportedly rising 15–25 %. | `risk_scorer.py` has no terrain branch | design brief §"Site Terrain" |
| **No labour productivity/availability modelling.** | absent | [2]: labour idling 58 %, low productivity 50 %, availability 42 % |
| **Single 80/20 hold-out; no cross-validation; no hyperparameter search.** | `train_model.py` | Rasila et al. [4] gained R² 0.896 → 0.955 from RandomizedSearchCV (R7) and used 5-fold CV |
| **Ordinal encoding of non-ordinal categoricals** (terrain, road access, roof type). Defensible for trees; finish grade alone is genuinely ordinal. | `feature_engineer.py` | Rasila et al. [4] deliberately use one-hot "to avoid imposing an ordinal relationship" |
| **`/retrain` is a stub**; PostgreSQL rate loader raises `NotImplementedError`. | `main.py`, `ictad_loader.py` | — |

### 6.2 Prioritised future work

1. Recalibrate the prediction interval — conformal prediction, or K-fold interval estimation
   after Rasila et al. [4], or tune α with depth/estimator reduction.
2. Replace the linear escalation stub with a CIDA-index model trained on the accumulating
   `price_history.csv`, and introduce provincial indices per [3].
3. Validate against real records: the UDA Middle-Income Housing register, contractor
   portfolios, and the 82-project UoM ERP dataset [4].
4. Cross-validation and hyperparameter search.
5. Calibrate risk premia and BOQ norms against completed-project data.

### 6.3 External validation available now (recommended, cheap)

The design brief compiles published 2025/26 per-square-foot construction cost bands for
Sri Lanka: **economy LKR 7,000–15,000/ft²; mid-range 15,000–22,000/ft²; luxury
22,000–35,000+/ft²**. Converting (× 10.7639 → per m²) gives roughly economy 75k–161k,
mid 161k–237k, luxury 237k–377k LKR/m². The pipeline already emits
`summary.cost_per_sqm_lkr`. **Plotting the 500 generated estimates against these bands by
finish grade is a real external sanity check** and would materially strengthen the paper —
it is the only validation currently available that is independent of the rule engine. It does
not fix the circularity, but it bounds it.

---

## 7. Source usage audit

Seven documents were supplied. Verdict on each, against the code as built.

| # | Source | Verdict | Where it is legitimately used |
|---|---|---|---|
| 1 | **National Policy on Construction** (CIDA / Act No. 33 of 2014) | **Used — motivation** | NPC 9 mandates IT systems for *"estimating and cost control"*. Best opening citation: the work answers a stated national policy objective. Also the legal basis for CIDA's rate-schedule authority (NPC 5), and NPC 9(iii)'s "industry-wide statistical database" justifies `price_history.csv` as a contribution. **No method or parameter derives from it — do not cite in Methodology.** |
| 2 | **Jayathilaka, Waidyasekara & Sirimewan (2021)**, IEOM Monterrey | **Used — heavily, design rationale** | See §7.1. The strongest justification source in the set. |
| 3 | **Nissanka & Wijesinghe (2022)**, SLIIT SICET | **Used — motivation + limitation** | Justifies the price scraper (if the national index doesn't track market prices, scrape actual prices) and the staleness/review gates. **Cite as a known limitation, not as an implemented method** — no regional index exists in the code. |
| 4 | **Rasila, Mahakalanda & Edirisooriya (2025)**, 13th World Construction Symposium | **Used — methodology** | See §7.2. The key local ML-cost-estimation reference. |
| 5 | **Muthumalki et al.**, KDU FBESS | **Not used for C02** | A delay paper — Component 04's territory. RII appears nowhere in `cost-estimation/`; its four-category delay taxonomy is unrelated to `RiskScorer`. At most one motivation sentence: it ranks "inaccurate time and cost estimating" as a delay cause, framing the C02→C03→C04 handoff. **Hand it to the C04 author.** |
| 6 | **Sivarajah (2021)**, JRTE 2(4) | **Not used for C02** | Delay mini-review, C04 territory. Marginal relevance: notes that delay produces "higher material costs through inflation". One motivation sentence at most. |
| 7 | **"Sri Lanka Construction Cost Data"** (untitled compilation) | **Used as the design spec — but NOT citable** | See §7.3. |

### 7.1 Jayathilaka et al. (2021) — the design-rationale backbone

12 semi-structured interviews (10 quantity surveyors, 2 civil engineers) across 6 building
projects at CIDA CS-2 graded firms; frequency analysis with a 25 % threshold.

**The headline finding for this paper:** material cost is **60–70 % of total cost overrun**,
labour **20–30 %** (11 of 12 respondents concurring). This single result justifies the entire
architectural emphasis — why Component 02 prices materials in depth (17-item schedule, 22
variants, live overlay) while treating labour as a coarse derived aggregate.

Direct source-to-feature mapping:

| Finding | Implementation |
|---|---|
| M5 material price fluctuation — joint top cause, 58 % | `scrape_stockpile.py` overlay; `PriceEscalationModel` |
| SM5 "use alternative materials with equivalent quality" | `MaterialCatalog`, 22 variants, `material_alternatives` in every response |
| SM27 "consider market conditions before planning to purchase" | `price_history.csv` time series; 45-day staleness rule |
| SM11 "maintain and update a vendor list" | supplier + URL captured per scraped sample |
| SM26 "calculate the theoretical requirement of the quantity of material" | Layer 1 BOQ Engine |
| SM4/SM18/SP14/SP32 accurate estimation, "take time to estimate" | the automated pipeline — the motivation claim |
| SP21 "planning for future risks" | Layer 4 `RiskScorer` + `ContingencyCalculator` |
| SP31 "address the foreign material price fluctuation" | escalation factor on every line rate |
| **M28 "incorrect norms" (25 %), M31 estimation errors** | **cited against ourselves** — our BOQ norms are unvalidated constants |
| L1/L3/L10/L11 labour productivity, idling, availability, skills | **not modelled** — declared scope boundary |

### 7.2 Rasila et al. (2025) — the methodological reference

Predicts *fuel cost percentage* over 82 projects (2008–2024) from a contractor ERP. **Different
target variable — we cannot claim to outperform it.** It is a methodology reference.

What was genuinely taken:

- **80/20 split with `random_state = 42`** — an exact match to `train_model.py` and
  `model_comparison.py`. Cite for the protocol.
- **Compare several supervised regressors, then select** — the structure of
  `model_comparison.py`.
- **Report a 90 % confidence interval alongside the point estimate, and treat interval
  tightness/stability as a first-class selection criterion** (their R8 chosen over the more
  accurate R7). This is precisely the design of `predict_interval` and
  `summary.lower_bound_lkr / upper_bound_lkr / confidence_level = 0.90`.
  **The mechanism differs and that difference is ours to claim:** Rasila derives the interval
  from K-fold fold-level predictions; we use direct quantile regression
  (`reg:quantileerror`, α = 0.05/0.95). Their approach is also our leading candidate fix for
  the 51 % coverage problem.
- **Their explicit future work — "exploring other ML techniques such as XGBoost or deep
  learning models could further enhance prediction capabilities"** — is the citation that
  justifies our model choice. Use it in Related Work.
- Metric set MAE/MSE/R² (we report a superset).
- Their gap statement (ML cost models neglect macroeconomic variables — inflation, price
  volatility, market demand) motivates our Layer 2. Note honestly that we do *not* ingest CIDA
  indices as a model feature, which is the very thing they added; their weak measured
  correlation (0.143) softens this.

Not taken: Random Forest as the production model, min-max scaling, one-hot encoding, K-fold
CV, hyperparameter search.

### 7.3 "Sri Lanka Construction Cost Data" — used, but do not cite it

This is an LLM-generated deep-research compilation: no author, no venue, no DOI, 26 "works
cited" all marked "accessed May 4, 2026". **It is not a citable reference for IEEE.** A copy
sits in the repo at `research/datasets/cost-records/`.

It is nonetheless the *de facto* design specification for several parts of the component:

- CIDA = former ICTAD (explains the repo's mixed naming)
- **The three-tier finish grade and its per-ft² bands** → `_GRADE_FACTORS`,
  `GRADE_DEFAULT_MATERIALS`, and the validation benchmark in §6.3
- **Terrain taxonomy flat/sloped/hilly/rocky** → verbatim `_TERRAIN_MAP`
- **Coastal proximity as a binary feature, with mechanism** (Grade 30+ concrete in saline
  environments, corrosion-resistant galvanised steel, Coast Conservation Department setbacks)
  → the `is_coastal` feature *and* the +5 % coastal risk premium, whose code comment
  paraphrases this passage
- Target dataset size 200–500 → `N_SAMPLES = 500`
- "XGBoost or Lasso Regression" recommended for Sri Lankan cost modelling → model choice

**The correct treatment: cite its primary sources, not the compilation.** Chase and cite
directly: the CIDA *Bulletin of Construction Statistics* (61 indices: 55 material, 3 labour,
3 plant; codes M1 cement, M8 sand, M13 reinforcement steel, L1/L2 labour, P1 diesel); the CIDA
price fluctuation formula; Parameswaran et al. (2019) on location factors; Abeysinghe (2010)
on the single national cost index. Its recommended data-acquisition roadmap (scrape
LankaPropertyWeb, adapt CPWD India / Kaggle) was **not** followed — the dataset is fully
synthetic — so none of those may be cited as data sources.

⚠️ **Discrepancy to resolve before quoting:** the compilation gives the CIDA price-fluctuation
fixed coefficient as **0.869** (for contracts ≤ LKR 10 M); Nissanka & Wijesinghe [3] give the
ICTAD fixed coefficient as **0.966**. These are likely different contract bands. Verify
against the primary CIDA bulletin before either number appears in the paper.

---

## 8. References (IEEE style — restricted to sources actually used)

### Primary sources supplied

[1] National Advisory Council on Construction, *National Policy on Construction*. Colombo, Sri Lanka: Ministry of Housing & Construction and Construction Industry Development Authority. Formulated under the Construction Industry Development Act No. 33 of 2014. [Add URL and access date.]

[2] R. D. W. W. Jayathilaka, K. G. A. S. Waidyasekara, and D. C. Sirimewan, "Impact of material and labour cost overruns on contractors' budgeted cost: The case of building construction projects in Sri Lanka," in *Proc. Int. Conf. Industrial Engineering and Operations Management (IEOM)*, Monterrey, Mexico, Nov. 3–5, 2021, pp. 1089–1100.

[3] H. D. N. M. Nissanka and T. Wijesinghe, "Regional relevancy of the CIDA price indices under the restrictions urged by the COVID-19 pandemic," in *Proc. SLIIT Int. Conf. Engineering and Technology*, vol. 1, Malabe, Sri Lanka, Feb. 9–11, 2022, pp. 144–155, doi: 10.54389/DCGT7296.

[4] K. A. M. Rasila, L. Mahakalanda, and M. W. Edirisooriya, "Predicting cost elements of construction projects using supervised machine learning techniques," in *Proc. 13th World Construction Symposium*, Sri Lanka, Aug. 15–16, 2025, pp. 1111–1124, doi: 10.31705/WCS.2025.83.

*Optional, motivation only — delay context for the C02→C03→C04 handoff:*

[5] G. A. T. Muthumalki, S. D. Jayasooriya, W. N. Kawmadi, and A. H. Lakmal, "Analyse factors affecting the delay in building construction projects in Sri Lanka; through the interaction of the project team," Faculty of Built Environment and Spatial Sciences, General Sir John Kotelawala Defence Univ., Sri Lanka, pp. 279–288. ⚠️ *Year and full proceedings title are not printed on the copy supplied — verify before submission.*

[6] T. Sivarajah, "Construction projects delays in Sri Lanka," *J. Research Technology & Engineering*, vol. 2, no. 4, pp. 25–29, 2021.

### Technical method references (must be added — currently absent from the repo)

[7] T. Chen and C. Guestrin, "XGBoost: A scalable tree boosting system," in *Proc. 22nd ACM SIGKDD Int. Conf. Knowledge Discovery and Data Mining*, San Francisco, CA, USA, 2016, pp. 785–794, doi: 10.1145/2939672.2939785.

[8] R. Koenker and G. Bassett, "Regression quantiles," *Econometrica*, vol. 46, no. 1, pp. 33–50, 1978, doi: 10.2307/1913643.

[9] S. M. Lundberg and S.-I. Lee, "A unified approach to interpreting model predictions," in *Proc. Advances in Neural Information Processing Systems (NeurIPS)*, 2017, pp. 4765–4774.

[10] S. M. Lundberg *et al.*, "From local explanations to global understanding with explainable AI for trees," *Nature Machine Intelligence*, vol. 2, no. 1, pp. 56–67, 2020, doi: 10.1038/s42256-019-0138-9.

### Recommended additions — reachable via [2] and [4], strongly on-topic

[11] N. V. Suchetha, Adithya, S. Ashik, Dhanush, and T. R. S. Guledagudda, "Home construction cost estimation using ML," *IRE Journals*, vol. 6, no. 11, pp. 536–543, 2023. *(Supports our finding that linear regression can outperform boosted trees here.)*

[12] B. Lim, M. P. Nepal, M. Skitmore, and B. Xiong, "Drivers of the accuracy of developers' early stage cost estimates in residential construction," *J. Financial Management of Property and Construction*, vol. 21, no. 1, pp. 4–20, 2016, doi: 10.1108/JFMPC-01-2015-0002. *(Best framing citation for what this component is.)*

[13] C. Stoy, S. Pollalis, and H. Schalcher, "Drivers for cost estimating in early design: Case study," *J. Construction Engineering and Management*, vol. 134, no. 1, pp. 32–39, 2008, doi: 10.1061/(ASCE)0733-9364(2008)134:1(32).

[14] D. J. Lowe, M. W. Emsley, and A. Harding, "Relationships between total construction cost and project strategic, site related and building definition variables," *J. Financial Management of Property and Construction*, vol. 11, no. 3, pp. 165–180, 2006, doi: 10.1108/13664380680001087. *(Justifies is_coastal / terrain / road_access as cost features.)*

[15] Y. G. Abed, T. M. Hasan, and R. N. Zehawi, "Machine learning algorithms for construction cost prediction: A systematic review," *Int. J. Nonlinear Analysis and Applications*, vol. 13, no. 2, pp. 2205–2218, 2022, doi: 10.22075/ijnaa.2022.27673.3684.

[16] S. T. Hashemi, O. M. Ebadati, and H. Kaur, "Cost estimation and prediction in construction projects: A systematic review on machine learning techniques," *SN Applied Sciences*, vol. 2, art. 1703, 2020, doi: 10.1007/s42452-020-03497-1.

[17] S. L. C. Miranda, E. D. R. Castillo, V. Gonzalez, and J. Adafin, "Predictive analytics for early-stage construction costs estimation," *Buildings*, vol. 12, no. 7, art. 1043, 2022, doi: 10.3390/buildings12071043.

[18] Construction Industry Development Authority, *Bulletin of Construction Statistics*. Colombo, Sri Lanka: CIDA. ⚠️ *Obtain the actual bulletin — currently known only second-hand through the design compilation.*

---

## 9. Reproducibility

```bash
cd cost-estimation
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python tests/generate_dataset.py       # 500 records -> research/datasets/cost-records/cost.csv
python scripts/train_model.py          # 3 XGBoost models -> models/*.json
python scripts/model_comparison.py     # comparison -> research/reports/ (SEE §0.1, §0.2)
python -m pytest tests/ -q             # 108 tests

uvicorn main:app --reload --port 8002  # docs at /docs
```

Fixed seeds: 42 for dataset generation, train/test split, and all model `random_state`.
Environment: Python 3.12, xgboost 2.1.4, scikit-learn 1.6.1, shap 0.46.0, pandas 2.2.3,
numpy 1.26.4, FastAPI 0.115.12.

---

## 10. Checklist before submission

**Done 30 Aug 2026:**

- [x] Fixed the R² computation in `model_comparison.py::evaluate_all`; regenerated `metrics.csv`
- [x] Replaced the hardcoded narrative in `generate_report()` with computed output
- [x] Rewrote `scripts/show_results.py` (was printing stale 0.759 / 2.67M figures)
- [x] Corrected the Model Selection section in `cost-estimation/README.md` **and** the root
      `README.md` (which carried a third, different set of numbers: 0.76 / −2.98)
- [x] Switched the comparison to the production 18-feature set
- [x] Added the noise-floor / R²-ceiling analysis (§5.2)
- [x] Removed the dead `StandardScaler`, the `train_neural_network()` stub and the "5 models"
      docstring claim; fixed a latent `ValueError` in `plot_comparison.py`
- [x] Aligned the coverage figure at 51 % across both READMEs
- [x] Confirmed 108/108 tests still pass

**Outstanding:**

- [ ] Add the §6.3 per-square-foot external validation plot — the only independent check available
- [ ] Address the 51 % interval coverage, or state it prominently as future work
- [ ] Verify the CIDA price-fluctuation fixed coefficient (0.869 vs 0.966 — sources disagree)
- [ ] Verify year and full venue for reference [5]
- [ ] Obtain the primary CIDA *Bulletin of Construction Statistics*
- [ ] Install seaborn/matplotlib if the comparison figures are wanted (neither is in
      `requirements.txt`; `plot_comparison.py` cannot currently run)
- [ ] Decide whether to add cross-validation and a hyperparameter search before submission
