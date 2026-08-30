#!/usr/bin/env python3
"""Generate visual comparison charts from model_comparison.py output."""

import sys
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

ROOT = Path(__file__).resolve().parent.parent
FIGURES_DIR = ROOT.parent / "research" / "reports" / "figures"
CSV_PATH = FIGURES_DIR / "metrics.csv"

if not CSV_PATH.exists():
    print(f"❌ Metrics CSV not found: {CSV_PATH}")
    print("   Run: python scripts/model_comparison.py (first)")
    sys.exit(1)

df = pd.read_csv(CSV_PATH)
print(f"✓ Loaded metrics from {CSV_PATH}")
print("\nData:")
print(df.to_string(index=False))

sns.set_style("whitegrid")
sns.set_palette("Set2")

# 1. MAE Comparison (Lower is Better)
fig, ax = plt.subplots(figsize=(10, 5))
df_mae = df.sort_values("MAE (LKR)", ascending=True)
colors = ["#2ecc71" if "Quantile" in m else "#3498db" for m in df_mae["Model"]]
bars = ax.barh(df_mae["Model"], df_mae["MAE (LKR)"] / 1e6, color=colors)
ax.set_xlabel("Mean Absolute Error (Million LKR)", fontsize=12, fontweight="bold")
ax.set_title("Model Accuracy Comparison (Lower MAE = Better)", fontsize=13, fontweight="bold")
for i, (idx, row) in enumerate(df_mae.iterrows()):
    ax.text(row["MAE (LKR)"] / 1e6 + 0.05, i, f"{row['MAE (LKR)'] / 1e6:.2f}M",
            va="center", fontsize=10, fontweight="bold")
plt.tight_layout()
plt.savefig(FIGURES_DIR / "01_mae_comparison.png", dpi=150, bbox_inches="tight")
print("\n✓ Saved: figures/01_mae_comparison.png")

# 2. R² Comparison (Higher is Better)
fig, ax = plt.subplots(figsize=(10, 5))
df_r2 = df.sort_values("R²", ascending=False)
colors = ["#2ecc71" if "Quantile" in m else "#e74c3c" for m in df_r2["Model"]]
bars = ax.barh(df_r2["Model"], df_r2["R²"], color=colors)
ax.set_xlabel("R² Score (Variance Explained)", fontsize=12, fontweight="bold")
ax.set_title("Model Fit Quality (Higher R² = Better)", fontsize=13, fontweight="bold")
ax.axvline(x=0, color="black", linestyle="--", linewidth=1, alpha=0.5, label="Baseline (mean)")
ax.set_xlim(0, 1.0)
for i, (idx, row) in enumerate(df_r2.iterrows()):
    val = row["R²"]
    x_pos = val - 0.15 if val > 0 else val + 0.05
    ax.text(x_pos, i, f"{val:.3f}", va="center", fontsize=10, fontweight="bold",
            color="white" if val > 0 else "black")
plt.legend(loc="lower right")
plt.tight_layout()
plt.savefig(FIGURES_DIR / "02_r2_comparison.png", dpi=150, bbox_inches="tight")
print("✓ Saved: figures/02_r2_comparison.png")

# 3. Training Time (Lower is Better, but trade-off with accuracy)
fig, ax = plt.subplots(figsize=(10, 5))
df_time = df.sort_values("Training Time (s)", ascending=True)
colors = ["#2ecc71" if "Quantile" in m else "#9b59b6" for m in df_time["Model"]]
bars = ax.barh(df_time["Model"], df_time["Training Time (s)"], color=colors)
ax.set_xlabel("Training Time (seconds)", fontsize=12, fontweight="bold")
ax.set_title("Training Speed (Lower = Faster)", fontsize=13, fontweight="bold")
for i, (idx, row) in enumerate(df_time.iterrows()):
    ax.text(row["Training Time (s)"] + 0.03, i, f"{row['Training Time (s)']:.2f}s",
            va="center", fontsize=10, fontweight="bold")
plt.tight_layout()
plt.savefig(FIGURES_DIR / "03_training_time.png", dpi=150, bbox_inches="tight")
print("✓ Saved: figures/03_training_time.png")

# 4. MAPE (Mean Absolute Percentage Error) - Lower is Better
fig, ax = plt.subplots(figsize=(10, 5))
df_mape = df.sort_values("MAPE (%)", ascending=True)
colors = ["#2ecc71" if "Quantile" in m else "#f39c12" for m in df_mape["Model"]]
bars = ax.barh(df_mape["Model"], df_mape["MAPE (%)"], color=colors)
ax.set_xlabel("MAPE — Mean Absolute Percentage Error (%)", fontsize=12, fontweight="bold")
ax.set_title("Prediction Error as % of Actual Cost (Lower = Better)", fontsize=13, fontweight="bold")
ax.axvline(x=15, color="red", linestyle="--", linewidth=1.5, alpha=0.6, label="15% threshold")
for i, (idx, row) in enumerate(df_mape.iterrows()):
    ax.text(row["MAPE (%)"] + 0.3, i, f"{row['MAPE (%)']:.1f}%",
            va="center", fontsize=10, fontweight="bold")
plt.legend(loc="lower right")
plt.tight_layout()
plt.savefig(FIGURES_DIR / "04_mape_comparison.png", dpi=150, bbox_inches="tight")
print("✓ Saved: figures/04_mape_comparison.png")

# 5. Feature Comparison Matrix (Radar-style or heatmap)
fig, ax = plt.subplots(figsize=(11, 6))

# Normalize metrics to 0-100 for visibility
df_norm = df.copy()
df_norm["MAE_norm"] = 100 - (df["MAE (LKR)"] / df["MAE (LKR)"].max() * 100)  # Inverted (lower is better)
df_norm["R²_norm"] = df["R²"].clip(lower=0) / df["R²"].abs().max() * 100  # Normalize R²
df_norm["Training Speed"] = 100 - (df["Training Time (s)"] / df["Training Time (s)"].max() * 100)  # Inverted
df_norm["MAPE_norm"] = 100 - (df["MAPE (%)"] / df["MAPE (%)"].max() * 100)  # Inverted

# Create comparison matrix
comparison = df_norm[["Model", "MAE_norm", "R²_norm", "Training Speed", "MAPE_norm"]].set_index("Model")
comparison.columns = ["Accuracy\n(MAE inverted)", "Fit Quality\n(R²)", "Speed\n(time inverted)", "Error %\n(MAPE inverted)"]

sns.heatmap(comparison.T, annot=True, fmt=".0f", cmap="RdYlGn", center=50, cbar_kws={"label": "Score (0-100)"}, ax=ax)
ax.set_title("Model Performance Scorecard (Higher = Better)\nGreen: Excellent | Red: Poor",
             fontsize=13, fontweight="bold", pad=15)
plt.tight_layout()
plt.savefig(FIGURES_DIR / "05_performance_scorecard.png", dpi=150, bbox_inches="tight")
print("✓ Saved: figures/05_performance_scorecard.png")

print("\n" + "="*80)
print("✅ All charts generated in: " + str(FIGURES_DIR))
print("="*80)
best_mae = df.loc[df["MAE (LKR)"].idxmin()]
best_r2_row = df.loc[df["R²"].idxmax()]
print("\nCharts:")
print(f"  1. figures/01_mae_comparison.png       — MAE (lowest: {best_mae['Model']}, "
      f"{best_mae['MAE (LKR)'] / 1e6:.2f}M LKR)")
print(f"  2. figures/02_r2_comparison.png        — R² (highest: {best_r2_row['Model']}, "
      f"{best_r2_row['R²']:.3f})")
print("  3. figures/03_training_time.png        — Training speed")
print("  4. figures/04_mape_comparison.png      — Percentage errors")
print("  5. figures/05_performance_scorecard.png — Overall comparison matrix")
