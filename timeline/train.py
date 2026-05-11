"""
train.py — Train ML models for all 8 construction phases.
Author : Hanfi A.M.M — IT22074454

Run from the timeline/ directory:
    python train.py

For each phase, trains Random Forest, XGBoost, and Gradient Boosting,
picks the winner by lowest RMSE, saves it as models/{col}_model.pkl.
Also saves: models/scaler.pkl  models/encoders.pkl  models/features.pkl
"""

import os, json, pickle, warnings
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
import xgboost as xgb

warnings.filterwarnings('ignore')

os.makedirs('models', exist_ok=True)
os.makedirs('output', exist_ok=True)

# ── Phase definitions (mirror of pipeline/phases.py PHASE_COLUMNS) ────────────
PHASE_COLS = [
    'preconstruction_weeks',
    'siteprep_weeks',
    'foundation_weeks',
    'structure_weeks',
    'envelope_weeks',
    'mep_weeks',
    'finishes_weeks',
    'external_weeks',
]

PHASE_LABELS = {
    'preconstruction_weeks': 'Pre-Construction',
    'siteprep_weeks':        'Site Preparation',
    'foundation_weeks':      'Foundations',
    'structure_weeks':       'Structure',
    'envelope_weeks':        'Envelope',
    'mep_weeks':             'MEP Rough-Ins',
    'finishes_weeks':        'Finishes',
    'external_weeks':        'External Works',
}

# ── Banner ─────────────────────────────────────────────────────────────────────
print("\n" + "=" * 65)
print("  Construction Timeline Prediction — Model Training")
print("  Hanfi A.M.M — IT22074454 — SLIIT")
print("=" * 65)

# ── Load data ──────────────────────────────────────────────────────────────────
DATA_PATH = os.path.join('data', 'construction_projects.csv')
if not os.path.exists(DATA_PATH):
    raise FileNotFoundError(
        f"{DATA_PATH} not found. Run: python data/generate_dataset.py"
    )

df = pd.read_csv(DATA_PATH)
print(f"\n  Loaded {len(df)} records from {DATA_PATH}")
print(f"  Total weeks — mean: {df['total_weeks'].mean():.1f}  "
      f"min: {df['total_weeks'].min():.1f}  max: {df['total_weeks'].max():.1f}\n")

# ── Encode categoricals ────────────────────────────────────────────────────────
le_district = LabelEncoder()
le_type     = LabelEncoder()
le_soil     = LabelEncoder()

df['district_enc'] = le_district.fit_transform(df['district'])
df['type_enc']     = le_type.fit_transform(df['construction_type'])
df['soil_enc']     = le_soil.fit_transform(df['soil_type'])

encoders = {
    'district': le_district,
    'construction_type': le_type,
    'soil_type': le_soil,
}
with open('models/encoders.pkl', 'wb') as f:
    pickle.dump(encoders, f)

# ── Feature engineering ────────────────────────────────────────────────────────
df['area_per_floor']    = df['built_up_area_sqft'] / df['num_floors']
df['cost_per_sqft']     = df['total_cost_lkr'] / df['built_up_area_sqft']
df['labor_per_sqft']    = df['labor_hours_total'] / df['built_up_area_sqft']
df['rooms_per_floor']   = df['num_rooms'] / df['num_floors']
df['bath_per_floor']    = df['num_bathrooms'] / df['num_floors']
df['complexity_score']  = (
    (df['built_up_area_sqft'] / 1_000) +
    (df['num_floors'] * 2.0) +
    (df['num_rooms'] * 0.4) +
    (df['num_bathrooms'] * 0.3)
)
df['resource_density']  = df['num_workers'] / df['complexity_score'].clip(lower=1)
df['experience_factor'] = df['contractor_experience_years'] / 30.0
df['is_monsoon']        = df['start_month'].isin([5, 6, 7, 8, 9, 10]).astype(int)
df['cost_ratio']        = df['material_cost_lkr'] / df['total_cost_lkr'].clip(lower=1)
df['worker_per_floor']  = df['num_workers'] / df['num_floors']

FEATURES = [
    # Raw inputs
    'built_up_area_sqft', 'num_floors', 'num_rooms', 'num_bathrooms',
    'total_cost_lkr', 'labor_hours_total', 'material_cost_lkr',
    'contractor_experience_years', 'start_month', 'num_workers', 'had_delays',
    # Encoded categoricals
    'district_enc', 'type_enc', 'soil_enc',
    # Engineered
    'area_per_floor', 'cost_per_sqft', 'labor_per_sqft',
    'rooms_per_floor', 'bath_per_floor', 'complexity_score',
    'resource_density', 'experience_factor', 'is_monsoon',
    'cost_ratio', 'worker_per_floor',
]

X = df[FEATURES].values
scaler = StandardScaler()
X_scaled = scaler.fit_transform(X)

with open('models/scaler.pkl', 'wb') as f:
    pickle.dump(scaler, f)
with open('models/features.pkl', 'wb') as f:
    pickle.dump(FEATURES, f)

print(f"  Features  : {len(FEATURES)}")
print(f"  Train/Test: 80% / 20%  (random_state=42)\n")

# ── Training loop ──────────────────────────────────────────────────────────────
def evaluate(y_true, y_pred):
    rmse = float(np.sqrt(mean_squared_error(y_true, y_pred)))
    mae  = float(mean_absolute_error(y_true, y_pred))
    mape = float(np.mean(np.abs((y_true - y_pred) / np.maximum(y_true, 0.5))) * 100)
    r2   = float(r2_score(y_true, y_pred))
    return rmse, mae, mape, r2

W = 18   # column width for phase label in table

print("─" * 78)
print(f"  {'Phase':<{W}} {'Model':<22} {'RMSE':>6} {'MAE':>6} {'MAPE':>7} {'R²':>7}")
print("─" * 78)

all_metrics = {}

for col in PHASE_COLS:
    label = PHASE_LABELS[col]
    y = df[col].values

    X_tr, X_te, y_tr, y_te = train_test_split(
        X_scaled, y, test_size=0.2, random_state=42
    )

    # ── Random Forest ──────────────────────────────────────────────────────────
    rf = RandomForestRegressor(
        n_estimators=400,
        max_depth=12,
        min_samples_split=3,
        min_samples_leaf=2,
        max_features='sqrt',
        random_state=42,
        n_jobs=-1,
    )
    rf.fit(X_tr, y_tr)
    rf_metrics = evaluate(y_te, rf.predict(X_te))

    # ── XGBoost ────────────────────────────────────────────────────────────────
    xg = xgb.XGBRegressor(
        n_estimators=400,
        max_depth=7,
        learning_rate=0.025,
        subsample=0.85,
        colsample_bytree=0.85,
        min_child_weight=2,
        reg_alpha=0.1,
        reg_lambda=1.0,
        random_state=42,
        verbosity=0,
        n_jobs=-1,
    )
    xg.fit(X_tr, y_tr, eval_set=[(X_te, y_te)], verbose=False)
    xg_metrics = evaluate(y_te, xg.predict(X_te))

    # ── Gradient Boosting ──────────────────────────────────────────────────────
    gb = GradientBoostingRegressor(
        n_estimators=400,
        max_depth=6,
        learning_rate=0.025,
        subsample=0.85,
        min_samples_split=4,
        min_samples_leaf=2,
        random_state=42,
    )
    gb.fit(X_tr, y_tr)
    gb_metrics = evaluate(y_te, gb.predict(X_te))

    candidates = [
        ('Random Forest',     rf, rf_metrics),
        ('XGBoost',           xg, xg_metrics),
        ('Gradient Boosting', gb, gb_metrics),
    ]
    best_name, best_model, best_m = min(candidates, key=lambda c: c[2][0])

    for name, _, m in candidates:
        winner = ' ✓' if name == best_name else ''
        lbl_col = label if name == candidates[0][0] else ''
        print(
            f"  {lbl_col:<{W}} {name + winner:<22}"
            f" {m[0]:>5.3f}w {m[1]:>5.3f}w {m[2]:>6.1f}% {m[3]:>7.3f}"
        )
    print()

    model_path = os.path.join('models', f'{col}_model.pkl')
    with open(model_path, 'wb') as f:
        pickle.dump(best_model, f)

    all_metrics[col] = {
        'phase_label': label,
        'best_model':  best_name,
        'rmse':  round(best_m[0], 4),
        'mae':   round(best_m[1], 4),
        'mape':  round(best_m[2], 2),
        'r2':    round(best_m[3], 4),
    }

# ── Target check ───────────────────────────────────────────────────────────────
print("─" * 78)
print("  TARGET CHECK   (MAPE < 15%   RMSE < 2 wks   R² > 0.85)")
print("─" * 78)

all_pass = True
for col, m in all_metrics.items():
    ok_mape = m['mape'] < 15.0
    ok_rmse = m['rmse'] <  2.0
    ok_r2   = m['r2']   >  0.85
    passed  = ok_mape and ok_rmse and ok_r2
    if not passed:
        all_pass = False
    status = '✓ PASS' if passed else '✗ FAIL'
    print(
        f"  {m['phase_label']:<{W}}  "
        f"MAPE={m['mape']:>5.1f}% {'✓' if ok_mape else '✗'}  "
        f"RMSE={m['rmse']:.3f}w {'✓' if ok_rmse else '✗'}  "
        f"R²={m['r2']:.3f} {'✓' if ok_r2 else '✗'}  "
        f"[{status}]"
    )

print("─" * 78)
print(f"  Overall: {'ALL TARGETS MET ✓' if all_pass else 'SOME TARGETS MISSED — consider more data or tuning'}")

# ── Best model summary ─────────────────────────────────────────────────────────
print("\n  Best model per phase:")
for col, m in all_metrics.items():
    print(f"    {m['phase_label']:<{W}}: {m['best_model']}")

# ── Save training results ──────────────────────────────────────────────────────
results_path = os.path.join('models', 'training_results.json')
with open(results_path, 'w') as f:
    json.dump(all_metrics, f, indent=2)

print(f"\n  Saved training results → {results_path}")
print("  Models saved → models/")
print("=" * 65)
print("  Training complete.")
print("=" * 65 + "\n")
