"""
Evaluate trained timeline prediction models.

Models evaluated:
1. Random Forest - phase duration multi-output prediction
2. XGBoost - phase duration multi-output prediction
3. PyTorch LSTM - total duration sequence prediction
"""

from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import torch
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from torch import nn


BASE_DIR = Path(__file__).resolve().parents[2]
DATASET_PATH = BASE_DIR / "data" / "residential_timeline_dataset.csv"
MODELS_DIR = BASE_DIR / "models"
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_PATH = OUTPUT_DIR / "model_evaluation_results.csv"

RF_MODEL_PATH = MODELS_DIR / "timeline_random_forest_model.pkl"
XGB_MODEL_PATH = MODELS_DIR / "timeline_xgboost_model.pkl"
LSTM_MODEL_PATH = MODELS_DIR / "timeline_lstm_pytorch.pt"
LSTM_X_SCALER_PATH = MODELS_DIR / "lstm_x_scaler.pkl"
LSTM_Y_SCALER_PATH = MODELS_DIR / "lstm_y_scaler.pkl"

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

LSTM_PHASE_SEQUENCE = [
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
]

TARGET_COLUMN = "total_duration_days"
RANDOM_STATE = 42


class ConstructionLSTM(nn.Module):
    """Runtime model definition matching train_lstm_pytorch.py."""

    def __init__(self) -> None:
        super().__init__()
        self.lstm = nn.LSTM(
            input_size=1,
            hidden_size=64,
            num_layers=1,
            batch_first=True,
        )
        self.dropout = nn.Dropout(0.2)
        self.fc1 = nn.Linear(64, 32)
        self.relu = nn.ReLU()
        self.fc2 = nn.Linear(32, 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        lstm_out, _ = self.lstm(x)
        last_timestep = lstm_out[:, -1, :]
        out = self.dropout(last_timestep)
        out = self.fc1(out)
        out = self.relu(out)
        out = self.fc2(out)
        return out


def validate_columns(df: pd.DataFrame) -> None:
    """Ensure all evaluation columns exist."""

    required_columns = sorted(set(INPUT_FEATURES + TARGET_COLUMNS + LSTM_PHASE_SEQUENCE))
    missing = [column for column in required_columns if column not in df.columns]
    if missing:
        raise ValueError("Dataset is missing required columns: " + ", ".join(missing))


def calculate_metrics(y_true, y_pred) -> dict[str, float]:
    """Calculate MAE, RMSE, R2, and MAPE."""

    y_true_array = np.asarray(y_true, dtype=float)
    y_pred_array = np.asarray(y_pred, dtype=float)

    mae = mean_absolute_error(y_true_array, y_pred_array)
    rmse = float(np.sqrt(mean_squared_error(y_true_array, y_pred_array)))
    r2 = r2_score(y_true_array, y_pred_array)
    mape = float(
        np.mean(
            np.abs((y_true_array - y_pred_array) / np.maximum(np.abs(y_true_array), 1))
        )
        * 100
    )

    return {
        "MAE": mae,
        "RMSE": rmse,
        "R2": r2,
        "MAPE": mape,
    }


def load_model_package(path: Path) -> dict:
    """Load a joblib model package."""

    if not path.exists():
        raise FileNotFoundError(f"Model file not found: {path}")
    package = joblib.load(path)
    if isinstance(package, dict) and "model" in package:
        return package
    return {
        "model": package,
        "input_features": INPUT_FEATURES,
        "target_columns": TARGET_COLUMNS,
    }


def evaluate_multioutput_model(
    model_name: str,
    model_path: Path,
    X_test: pd.DataFrame,
    y_test: pd.DataFrame,
) -> dict:
    """Evaluate Random Forest or XGBoost multi-output model."""

    package = load_model_package(model_path)
    model = package["model"]
    feature_columns = package.get("input_features", INPUT_FEATURES)
    target_columns = package.get("target_columns", TARGET_COLUMNS)

    predictions = model.predict(X_test[feature_columns])
    metrics = calculate_metrics(y_test[target_columns], predictions)

    return {
        "Model": model_name,
        "Prediction Type": "Phase durations + total duration",
        **metrics,
    }


def evaluate_lstm_model(df: pd.DataFrame) -> dict:
    """Evaluate the PyTorch LSTM total-duration model."""

    if not LSTM_MODEL_PATH.exists():
        raise FileNotFoundError(f"LSTM model file not found: {LSTM_MODEL_PATH}")
    if not LSTM_X_SCALER_PATH.exists() or not LSTM_Y_SCALER_PATH.exists():
        raise FileNotFoundError("LSTM scaler files are missing.")

    X_raw = df[LSTM_PHASE_SEQUENCE].values.astype(np.float32)
    y_raw = df[[TARGET_COLUMN]].values.astype(np.float32)

    x_scaler = joblib.load(LSTM_X_SCALER_PATH)
    y_scaler = joblib.load(LSTM_Y_SCALER_PATH)

    X_scaled = x_scaler.transform(X_raw).astype(np.float32)
    y_scaled = y_scaler.transform(y_raw).astype(np.float32)
    X_lstm = X_scaled.reshape(-1, len(LSTM_PHASE_SEQUENCE), 1)

    _, X_test, _, y_test = train_test_split(
        X_lstm,
        y_scaled,
        test_size=0.2,
        random_state=RANDOM_STATE,
    )

    checkpoint = torch.load(
        LSTM_MODEL_PATH,
        map_location=torch.device("cpu"),
        weights_only=False,
    )
    model = ConstructionLSTM()
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()

    with torch.no_grad():
        predictions_scaled = model(torch.tensor(X_test, dtype=torch.float32)).numpy()

    predictions = y_scaler.inverse_transform(predictions_scaled)
    y_test_actual = y_scaler.inverse_transform(y_test)
    metrics = calculate_metrics(y_test_actual, predictions)

    return {
        "Model": "PyTorch LSTM",
        "Prediction Type": "Total duration from phase sequence",
        **metrics,
    }


def print_results_table(results: list[dict]) -> None:
    """Print a clear console results table."""

    print("\nModel Evaluation Results")
    print("=" * 92)
    print(
        f"{'Model':<18} | {'Prediction Type':<38} | "
        f"{'MAE':>8} | {'RMSE':>8} | {'R2':>8} | {'MAPE':>8}"
    )
    print("-" * 92)
    for row in results:
        print(
            f"{row['Model']:<18} | {row['Prediction Type']:<38} | "
            f"{row['MAE']:>8.4f} | {row['RMSE']:>8.4f} | "
            f"{row['R2']:>8.4f} | {row['MAPE']:>7.2f}%"
        )
    print("=" * 92)


def main() -> None:
    """Run evaluation for Random Forest, XGBoost, and PyTorch LSTM."""

    if not DATASET_PATH.exists():
        raise FileNotFoundError(
            f"Dataset not found: {DATASET_PATH}. "
            "Run app/training/generate_synthetic_dataset.py first."
        )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(DATASET_PATH)
    validate_columns(df)

    X = df[INPUT_FEATURES]
    y = df[TARGET_COLUMNS]

    _, X_test, _, y_test = train_test_split(
        X,
        y,
        test_size=0.2,
        random_state=RANDOM_STATE,
    )

    results = [
        evaluate_multioutput_model("Random Forest", RF_MODEL_PATH, X_test, y_test),
        evaluate_multioutput_model("XGBoost", XGB_MODEL_PATH, X_test, y_test),
        evaluate_lstm_model(df),
    ]

    results_df = pd.DataFrame(results)
    results_df.to_csv(OUTPUT_PATH, index=False)

    print_results_table(results)
    print(f"\nSaved evaluation results to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
