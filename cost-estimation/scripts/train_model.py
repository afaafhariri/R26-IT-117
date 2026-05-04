#!/usr/bin/env python3
"""
Train XGBoost cost prediction models on the generated dataset.

Trains three models:
  - Point estimate      (objective: reg:squarederror)
  - Lower bound p5      (objective: reg:quantileerror, alpha=0.05)
  - Upper bound p95     (objective: reg:quantileerror, alpha=0.95)

Run from the cost-estimation/ directory:
    python scripts/train_model.py

Input:  research/datasets/cost-records/cost.csv
Output: models/xgboost_point.json
        models/xgboost_p5.json
        models/xgboost_p95.json
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.metrics import r2_score, mean_absolute_percentage_error

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from layers.layer3_ml_prediction.xgboost_model import XGBoostCostModel
from layers.layer3_ml_prediction.feature_engineer import FeatureEngineer

DATASET_PATH = ROOT.parent / "research" / "datasets" / "cost-records" / "cost.csv"
MODELS_DIR = ROOT / "models"
FEATURE_COLS = FeatureEngineer.feature_names()


def train() -> None:
    print(f"Loading dataset: {DATASET_PATH}")
    if not DATASET_PATH.exists():
        print("ERROR: Dataset not found. Run scripts/generate_dataset.py first.")
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

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, random_state=42
    )
    print(f"\nTrain / Test split: {len(X_train)} / {len(X_test)}")

    model = XGBoostCostModel()
    print("\nTraining XGBoost point + quantile models...")
    model.train(X_train, y_train)

    # --- Evaluation ---
    y_pred = np.array([model.predict(X_test.iloc[[i]]) for i in range(len(X_test))])
    r2 = r2_score(y_test, y_pred)
    mape = mean_absolute_percentage_error(y_test, y_pred) * 100

    # Interval coverage: fraction of test labels inside the 90% PI
    lowers, uppers = zip(*[model.predict_interval(X_test.iloc[[i]]) for i in range(len(X_test))])
    coverage = float(np.mean(
        (y_test.values >= np.array(lowers)) & (y_test.values <= np.array(uppers))
    ))

    print("\n" + "=" * 50)
    print("  EVALUATION — held-out test set")
    print("=" * 50)
    print(f"  R²              : {r2:.4f}  ({r2 * 100:.1f}%)")
    print(f"  MAPE            : {mape:.2f}%")
    print(f"  90% PI coverage : {coverage * 100:.1f}%")
    print("=" * 50)

    if r2 >= 0.60:
        print(f"\n  Accuracy target met (R² {r2 * 100:.1f}% >= 60%).")
    else:
        print(f"\n  WARNING: R² {r2 * 100:.1f}% is below the 60% target.")

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    model.save(str(MODELS_DIR))

    print(f"\nModels saved to: {MODELS_DIR}/")
    print("  xgboost_point.json")
    print("  xgboost_p5.json")
    print("  xgboost_p95.json")
    print("\nAPI is ready. Start with: uvicorn main:app --reload")


if __name__ == "__main__":
    train()
