#!/usr/bin/env python3
"""
Train XGBoost cost prediction models on the generated dataset.

Trains the point model plus five quantile models, and computes the conformal
calibration offsets that make the reported intervals achieve their nominal coverage.

The quantile models are fitted on a proper-training subset; a held-out calibration
subset supplies the offsets. Retraining without recomputing the offsets silently voids
the coverage guarantee, so the two always happen together here.

Run from the cost-estimation/ directory:
    python scripts/train_model.py

Input:  research/datasets/cost-records/cost.csv
Output: models/xgboost_point.json
        models/xgboost_q05.json, q25, q75, q90, q95
        models/conformal_offsets.json
"""

import sys
from pathlib import Path
from typing import cast

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.metrics import r2_score, mean_absolute_percentage_error

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from layers.layer3_ml_prediction.xgboost_model import XGBoostCostModel  # noqa: E402
from layers.layer3_ml_prediction.feature_engineer import FeatureEngineer  # noqa: E402

DATASET_PATH = ROOT.parent / "research" / "datasets" / "cost-records" / "cost.csv"
MODELS_DIR = ROOT / "models"
FEATURE_COLS = FeatureEngineer.feature_names()


def train() -> None:
    print(f"Loading dataset: {DATASET_PATH}")
    if not DATASET_PATH.exists():
        print("ERROR: Dataset not found. Run tests/generate_dataset.py first.")
        sys.exit(1)

    df = pd.read_csv(DATASET_PATH)
    print(f"Loaded {len(df)} records.")

    missing = [c for c in FEATURE_COLS if c not in df.columns]
    if missing:
        print(f"ERROR: Missing feature columns: {missing}")
        sys.exit(1)

    X = df[FEATURE_COLS].copy()
    y = df["grand_total_lkr"].copy()

    print(f"Features : {X.shape[1]}")
    print(f"Target   : LKR {y.min():,.0f} – {y.max():,.0f}  (mean {y.mean():,.0f})")

    splits = train_test_split(X, y, test_size=0.20, random_state=42)
    X_train = cast(pd.DataFrame, splits[0])
    X_test  = cast(pd.DataFrame, splits[1])
    y_train = cast(pd.Series,    splits[2])
    y_test  = cast(pd.Series,    splits[3])
    print(f"\nTrain / Test split: {len(X_train)} / {len(X_test)}")

    model = XGBoostCostModel()
    print("\nTraining XGBoost point + quantile models...")
    model.train(X_train, y_train)

    # --- Evaluation ---
    y_pred = np.array([model.predict(X_test.iloc[[i]]) for i in range(len(X_test))])
    r2 = r2_score(y_test, y_pred)
    mape = mean_absolute_percentage_error(y_test, y_pred) * 100
    y_true = y_test.values

    print("\n" + "=" * 62)
    print("  EVALUATION — held-out test set")
    print("=" * 62)
    print(f"  Point estimate   R² {r2:.4f}   MAPE {mape:.2f}%")
    print()
    print(f"  {'interval':<12}{'nominal':>9}{'empirical':>11}{'mean width':>13}")

    for level in (0.50, 0.90):
        bounds = [model.predict_interval(X_test.iloc[[i]], level=level)
                  for i in range(len(X_test))]
        lo = np.array([b[0] for b in bounds])
        hi = np.array([b[1] for b in bounds])
        cov = float(np.mean((y_true >= lo) & (y_true <= hi))) * 100
        width = float(np.mean((hi - lo) / np.maximum(y_pred, 1.0))) * 100
        print(f"  {'two-sided':<12}{level * 100:>8.0f}%{cov:>10.1f}%{width:>12.1f}%")

    budget = np.array([model.predict_budget(X_test.iloc[[i]]) for i in range(len(X_test))])
    below = float(np.mean(y_true <= budget)) * 100
    print(f"  {'budget (1-s)':<12}{90:>8.0f}%{below:>10.1f}%{'—':>12}")
    print("=" * 62)
    print(f"  Conformal offsets (log space): {model._conformal}")

    if not model.is_calibrated:
        print("\n  WARNING: calibration did not run — intervals carry no coverage guarantee.")
    if r2 >= 0.60:
        print(f"\n  Accuracy target met (R² {r2 * 100:.1f}% >= 60%).")
    else:
        print(f"\n  WARNING: R² {r2 * 100:.1f}% is below the 60% target.")

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    model.save(str(MODELS_DIR))

    print(f"\nModels saved to: {MODELS_DIR}/")
    for f in sorted(MODELS_DIR.glob("*.json")):
        print(f"  {f.name}")
    print("\nAPI is ready. Start with: uvicorn main:app --reload")


if __name__ == "__main__":
    train()
