#!/usr/bin/env python3
"""
Generate 500 CIDA-calibrated training records for the XGBoost cost model.

Training labels are produced by running randomised building configurations through
Layers 1 (BOQ), 2 (Rate Engine), and 4 (Risk + Contingency), all calibrated to
CIDA 2024-Q4 published unit rates. Lognormal noise (sigma=0.15) is applied to the
grand total to simulate real-world contractor and market variance.

Run from the cost-estimation/ directory:
    python scripts/generate_dataset.py

Output: research/datasets/cost-records/cost.csv
"""

import math
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Allow imports from cost-estimation root
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from layers.layer1_boq.boq_engine import BOQEngine
from layers.layer2_rate_engine.rate_engine import RateEngine
from layers.layer3_ml_prediction.feature_engineer import FeatureEngineer
from layers.layer4_risk_adjuster.risk_scorer import RiskScorer
from layers.layer4_risk_adjuster.contingency import ContingencyCalculator

logging.basicConfig(level=logging.WARNING)

OUTPUT_PATH = ROOT.parent / "research" / "datasets" / "cost-records" / "cost.csv"
N_SAMPLES = 500
RANDOM_SEED = 42

DISTRICTS = [
    "Colombo", "Gampaha", "Kalutara", "Kandy", "Matale", "Nuwara Eliya",
    "Galle", "Matara", "Hambantota", "Jaffna", "Kilinochchi", "Mannar",
    "Vavuniya", "Mullaitivu", "Batticaloa", "Ampara", "Trincomalee",
    "Kurunegala", "Puttalam", "Anuradhapura", "Polonnaruwa", "Badulla",
    "Monaragala", "Ratnapura", "Kegalle",
]

# Approximate residential construction activity per district (normalised below)
_RAW_WEIGHTS = [
    15, 10, 6, 7, 3, 2, 5, 4, 3, 3, 1, 1, 2, 1, 2, 2, 2, 5, 3, 4, 2, 3, 2, 4, 4,
]

COASTAL_DISTRICTS = {
    "Colombo", "Gampaha", "Kalutara", "Galle", "Matara",
    "Hambantota", "Puttalam", "Jaffna", "Trincomalee", "Batticaloa", "Ampara",
}

TERRAIN_BY_DISTRICT = {
    "Colombo": ["flat"],
    "Gampaha": ["flat"],
    "Kalutara": ["flat", "sloped"],
    "Kandy": ["hilly", "sloped"],
    "Matale": ["hilly", "sloped"],
    "Nuwara Eliya": ["hilly", "rocky"],
    "Galle": ["flat", "sloped"],
    "Matara": ["flat", "sloped"],
    "Hambantota": ["flat"],
    "Jaffna": ["flat"],
    "Kilinochchi": ["flat"],
    "Mannar": ["flat"],
    "Vavuniya": ["flat", "sloped"],
    "Mullaitivu": ["flat"],
    "Batticaloa": ["flat"],
    "Ampara": ["flat", "sloped"],
    "Trincomalee": ["flat", "sloped"],
    "Kurunegala": ["flat", "sloped"],
    "Puttalam": ["flat"],
    "Anuradhapura": ["flat"],
    "Polonnaruwa": ["flat"],
    "Badulla": ["hilly", "rocky"],
    "Monaragala": ["hilly", "sloped"],
    "Ratnapura": ["hilly", "rocky"],
    "Kegalle": ["hilly", "sloped"],
}


def _sample_schema(rng: np.random.Generator, district_weights: np.ndarray) -> dict:
    """Sample a randomised but realistic building schema dict."""
    district = str(rng.choice(DISTRICTS, p=district_weights))

    # Footprint: log-normal centred on 120 m² (typical Sri Lankan house)
    footprint_sqm = float(np.clip(rng.lognormal(np.log(120), 0.4), 50, 350))

    floors = int(rng.choice([1, 2, 3, 4], p=[0.60, 0.28, 0.09, 0.03]))

    # Perimeter derived from footprint; shape factor > 1 for non-square plans
    shape_factor = float(rng.uniform(1.0, 1.4))
    perimeter = round(4 * math.sqrt(footprint_sqm) * shape_factor, 1)

    floor_height = round(float(rng.uniform(2.8, 3.5)), 2)
    wall_height = floor_height
    excavation_depth = round(float(rng.uniform(1.0, 2.0)), 2)

    finish_grade = str(rng.choice(["economy", "mid", "luxury"], p=[0.25, 0.55, 0.20]))
    roof_type = str(rng.choice(["flat", "gable", "hip", "mansard"], p=[0.15, 0.50, 0.25, 0.10]))

    is_coastal = bool(district in COASTAL_DISTRICTS and rng.random() < 0.65)
    terrain = str(rng.choice(TERRAIN_BY_DISTRICT.get(district, ["flat"])))
    road_access = str(rng.choice(["paved", "gravel", "track", "none"], p=[0.60, 0.25, 0.10, 0.05]))
    plot_area = round(float(np.clip(rng.lognormal(np.log(400), 0.6), 80, 2000)), 1)

    # Openings: 8–20% of approximate external wall area
    wall_area_approx = perimeter * wall_height * floors
    openings_sqm = round(float(wall_area_approx * rng.uniform(0.08, 0.20)), 1)
    internal_wall_length = round(float(footprint_sqm * rng.uniform(0.25, 0.65)), 1)

    room_count = int(rng.choice(range(2, 9), p=[0.05, 0.15, 0.25, 0.25, 0.15, 0.10, 0.05]))
    bathroom_count = max(1, int(rng.choice([1, 2, 3, 4], p=[0.30, 0.45, 0.18, 0.07])))

    bedrooms = max(0, room_count - 2)
    rooms = {
        "living_room": 1,
        "master_bedroom": 1,
        "bedroom": max(0, bedrooms - 1),
        "kitchen": 1,
        "bathroom": bathroom_count,
        "dining_room": 1 if room_count > 3 else 0,
        "study": 1 if room_count > 5 else 0,
        "garage": 1 if rng.random() < 0.15 else 0,
    }

    return {
        "footprint_sqm": round(footprint_sqm, 1),
        "perimeter": perimeter,
        "floors": floors,
        "floor_height": floor_height,
        "wall_height": wall_height,
        "excavation_depth": excavation_depth,
        "column_count": 0,
        "openings_sqm": openings_sqm,
        "internal_wall_length": internal_wall_length,
        "finish_grade": finish_grade,
        "roof_type": roof_type,
        "district": district,
        "is_coastal": is_coastal,
        "terrain": terrain,
        "road_access": road_access,
        "plot_area": plot_area,
        "rooms": rooms,
        "bathroom_count": bathroom_count,
        "room_count": room_count,
        "base_rate_date": "2024-10-01",
        "target_date": "2025-01-01",
    }


def generate(n: int = N_SAMPLES) -> pd.DataFrame:
    rng = np.random.default_rng(RANDOM_SEED)
    weights = np.array(_RAW_WEIGHTS, dtype=float)
    weights /= weights.sum()

    boq_engine = BOQEngine()
    rate_engine = RateEngine()
    feature_engineer = FeatureEngineer()
    risk_scorer = RiskScorer()
    contingency_calc = ContingencyCalculator()

    records = []
    failed = 0

    for i in range(n):
        schema = _sample_schema(rng, weights)
        finish_grade = schema["finish_grade"]

        try:
            # Layer 1: quantities
            boq = boq_engine.run(schema)

            # Layer 2: priced trade breakdown
            rates = rate_engine.price_boq(
                boq,
                district=schema["district"],
                base_date=schema["base_rate_date"],
                target_date=schema["target_date"],
            )
            direct_cost = rates.get("direct_cost_lkr", 0.0)
            if direct_cost <= 0:
                failed += 1
                continue

            # Feature matrix (X for training)
            features_df = feature_engineer.build_features(boq, schema, finish_grade)
            features = features_df.iloc[0].to_dict()

            # Layer 4: risk + contingency → grand total (training target y)
            risk = risk_scorer.score(schema, schema, finish_grade)
            contingency = contingency_calc.calculate(direct_cost, risk["total_risk_pct"])
            grand_total = contingency["grand_total_lkr"]

            # Lognormal noise: simulates contractor markup and market variance
            noise_factor = float(rng.lognormal(0.0, 0.15))
            noisy_total = round(grand_total * noise_factor, 2)

            record = {
                # Input parameters (for traceability and Tier 1/2 data merging)
                "footprint_sqm": schema["footprint_sqm"],
                "perimeter": schema["perimeter"],
                "floors": schema["floors"],
                "finish_grade": finish_grade,
                "district": schema["district"],
                "is_coastal": int(schema["is_coastal"]),
                "terrain": schema["terrain"],
                "road_access": schema["road_access"],
                "plot_area": schema["plot_area"],
                "bathroom_count": schema["bathroom_count"],
                "room_count": schema["room_count"],
                # 19 ML feature columns
                **features,
                # Targets
                "direct_cost_lkr": round(direct_cost, 2),
                "grand_total_lkr": noisy_total,
            }
            records.append(record)

        except Exception as exc:
            failed += 1
            print(f"  Warning: record {i} failed — {exc}")

        if (i + 1) % 100 == 0:
            print(f"  Generated {len(records)}/{n} records (failed: {failed})...")

    return pd.DataFrame(records)


if __name__ == "__main__":
    print(f"Generating {N_SAMPLES} CIDA-calibrated training records...")
    print(f"Noise model: lognormal sigma=0.15 (contractor/market variance)")
    print()

    df = generate(N_SAMPLES)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_PATH, index=False)

    print(f"\nDataset saved → {OUTPUT_PATH}")
    print(f"Shape: {df.shape[0]} records × {df.shape[1]} columns")
    print(f"\nCost statistics (grand_total_lkr):")
    print(f"  Min  : LKR {df['grand_total_lkr'].min():>15,.0f}")
    print(f"  Max  : LKR {df['grand_total_lkr'].max():>15,.0f}")
    print(f"  Mean : LKR {df['grand_total_lkr'].mean():>15,.0f}")
    print(f"  Median: LKR {df['grand_total_lkr'].median():>14,.0f}")
    print(f"\nTop districts in dataset:")
    print(df["district"].value_counts().head(8).to_string())
    print(f"\nFinish grade distribution:")
    print(df["finish_grade"].value_counts().to_string())
