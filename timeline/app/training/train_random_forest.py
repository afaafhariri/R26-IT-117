"""
Train a Random Forest model for residential construction timeline prediction.

The model learns to predict phase durations and total project duration from the
synthetic residential construction dataset generated for the timeline component.
"""

from __future__ import annotations

from pathlib import Path

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split


BASE_DIR = Path(__file__).resolve().parents[2]
DATASET_PATH = BASE_DIR / "data" / "residential_timeline_dataset.csv"
MODELS_DIR = BASE_DIR / "models"
MODEL_PATH = MODELS_DIR / "timeline_random_forest_model.pkl"

INPUT_FEATURES = [
    "num_floors",
    "floor_area_sqm",
    "built_up_area_sqft",
    "room_count",
    "bathroom_count",
    "foundation_excavation_m3",
    "foundation_concrete_m3",
    "total_concrete_m3",
    "steel_kg_estimate",
    "total_brickwork_m3",
    "roof_area_sqm",
    "floor_tile_sqm",
    "wall_plaster_sqm",
    "paint_sqm",
    "electrical_points",
    "total_plumbing_fixtures",
    "total_labour_days",
    "structural_complexity_score",
]

TARGET_COLUMNS = [
    "foundation_days",
    "structure_days",
    "masonry_days",
    "roofing_days",
    "electrical_days",
    "plumbing_days",
    "plastering_days",
    "finishing_days",
    "painting_days",
    "external_work_days",
    "handover_days",
    "total_duration_days",
]


def validate_columns(df: pd.DataFrame) -> None:
    """Fail early if the CSV is missing required feature or target columns."""

    required_columns = INPUT_FEATURES + TARGET_COLUMNS
    missing_columns = [column for column in required_columns if column not in df.columns]
    if missing_columns:
        raise ValueError(
            "Dataset is missing required columns: " + ", ".join(missing_columns)
        )


def main() -> None:
    """Load data, train Random Forest, evaluate, and save the model."""

    if not DATASET_PATH.exists():
        raise FileNotFoundError(
            f"Dataset not found: {DATASET_PATH}. "
            "Run app/training/generate_synthetic_dataset.py first."
        )

    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(DATASET_PATH)
    validate_columns(df)

    X = df[INPUT_FEATURES]
    y = df[TARGET_COLUMNS]

    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=0.2,
        random_state=42,
    )

    model = RandomForestRegressor(
        n_estimators=300,
        random_state=42,
        max_depth=None,
        min_samples_split=2,
        min_samples_leaf=1,
        n_jobs=-1,
    )

    print("Training Random Forest timeline model...")
    model.fit(X_train, y_train)

    predictions = model.predict(X_test)
    mae = mean_absolute_error(y_test, predictions)
    r2 = r2_score(y_test, predictions)

    model_package = {
        "model": model,
        "input_features": INPUT_FEATURES,
        "target_columns": TARGET_COLUMNS,
        "mae": mae,
        "r2_score": r2,
    }
    joblib.dump(model_package, MODEL_PATH)

    print("\nRandom Forest Training Completed")
    print("=" * 50)
    print(f"Dataset size       : {len(df)} records")
    print(f"Train size         : {len(X_train)} records")
    print(f"Test size          : {len(X_test)} records")
    print(f"Input features     : {INPUT_FEATURES}")
    print(f"Target columns     : {TARGET_COLUMNS}")
    print(f"MAE                : {mae:.4f} days")
    print(f"R2 score           : {r2:.4f}")
    print(f"Saved model path   : {MODEL_PATH}")


if __name__ == "__main__":
    main()
