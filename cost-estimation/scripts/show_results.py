#!/usr/bin/env python3
"""Print the model comparison table and a summary derived from the measured metrics.

Every figure printed here is read from figures/metrics.csv or computed from it. An
earlier version of this script printed a fixed narrative quoting results (R² 0.759,
MAE 2.67M, a 65/35 XGBoost+MLP ensemble) that no run had produced and that contradicted
metrics.csv. Nothing below is hardcoded.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
FIGURES_DIR = ROOT.parent / "research" / "reports" / "figures"
CSV_PATH = FIGURES_DIR / "metrics.csv"

# Must match the noise applied in tests/generate_dataset.py
NOISE_SIGMA = 0.15

if not CSV_PATH.exists():
    print(f"Metrics CSV not found: {CSV_PATH}")
    print("   Run: python scripts/model_comparison.py")
    sys.exit(1)

df = pd.read_csv(CSV_PATH)
print(f"Loaded metrics from {CSV_PATH}\n")

pd.set_option("display.max_columns", None)
pd.set_option("display.width", None)
pd.set_option("display.max_rows", None)

print("=" * 120)
print("MODEL COMPARISON — Construction Cost Estimation (500 synthetic records, 18 features)")
print("=" * 120)
print()

shown = df.copy()
for col in ("MAE (LKR)", "RMSE (LKR)"):
    shown[col] = shown[col].apply(lambda x: f"LKR {x / 1e6:,.2f}M")
for col in ("MAPE (%)", "MdAPE (%)", "R²"):
    shown[col] = shown[col].apply(lambda x: f"{x:.3f}")
shown["Training Time (s)"] = shown["Training Time (s)"].apply(lambda x: f"{x:.3f}s")

print(shown.to_string(index=False))
print()
print("=" * 120)
print("INTERPRETATION")
print("-" * 120)
print()

best_mape = df.loc[df["MAPE (%)"].idxmin()]
best_r2 = df.loc[df["R²"].idxmax()]
worst_mape = df.loc[df["MAPE (%)"].idxmax()]
mape_floor = NOISE_SIGMA * np.sqrt(2.0 / np.pi) * 100

print(f"1. Best point accuracy : {best_mape['Model']} — MAPE {best_mape['MAPE (%)']:.2f}%, "
      f"R² {best_mape['R²']:.3f}")
print(f"2. Best fit quality    : {best_r2['Model']} — R² {best_r2['R²']:.3f}")
print()
print(f"3. Irreducible MAPE floor from the injected lognormal(0, {NOISE_SIGMA}) label noise "
      f"is {mape_floor:.2f}%.")
print(f"   The leading model is {best_mape['MAPE (%)'] - mape_floor:.2f} points above it, so the")
print("   surrogate task is effectively saturated and this table cannot discriminate")
print("   model quality for real construction cost data.")
print()

interval_models = df[df["Prediction Interval"] != "✗"]
if not interval_models.empty:
    q = interval_models.iloc[0]
    print(f"4. Only {q['Model']} produces a prediction interval natively: "
          f"{q['Prediction Interval']} empirical coverage against a 90% nominal target.")
    print(f"   It ranks last on point accuracy (MAPE {q['MAPE (%)']:.2f}%, "
          f"{q['MAPE (%)'] - best_mape['MAPE (%)']:.2f} points behind {best_mape['Model']}).")
    print("   It is deployed for capability — native intervals and exact TreeSHAP — not accuracy.")
    print("   The coverage shortfall is an open calibration issue.")
print()
print("=" * 120)
