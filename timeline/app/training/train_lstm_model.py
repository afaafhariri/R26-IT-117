"""
Train an LSTM model for construction timeline duration prediction.

The LSTM learns the sequence of construction phase durations and predicts the
total project duration in days.
"""

from __future__ import annotations

import os
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import MinMaxScaler

try:
    from tensorflow.keras.layers import LSTM, Dense, Dropout
    from tensorflow.keras.models import Sequential
except ImportError as exc:
    raise SystemExit(
        "TensorFlow could not be loaded in this Python environment. "
        "Install/fix TensorFlow first, then rerun this script. "
        "On Windows this is commonly caused by an incompatible TensorFlow build, "
        "missing Microsoft Visual C++ Redistributable, or CPU instruction support."
    ) from exc


os.environ["TF_CPP_MIN_LOG_LEVEL"] = "2"

BASE_DIR = Path(__file__).resolve().parents[2]
DATASET_PATH = BASE_DIR / "data" / "residential_timeline_dataset.csv"
MODELS_DIR = BASE_DIR / "models"
MODEL_PATH = MODELS_DIR / "timeline_lstm_model.keras"
X_SCALER_PATH = MODELS_DIR / "lstm_x_scaler.pkl"
Y_SCALER_PATH = MODELS_DIR / "lstm_y_scaler.pkl"

PHASE_DURATION_COLUMNS = [
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
TIMESTEPS = len(PHASE_DURATION_COLUMNS)
FEATURES_PER_TIMESTEP = 1


def validate_columns(df: pd.DataFrame) -> None:
    """Check whether all phase sequence and target columns exist."""

    required_columns = PHASE_DURATION_COLUMNS + [TARGET_COLUMN]
    missing_columns = [column for column in required_columns if column not in df.columns]
    if missing_columns:
        raise ValueError(
            "Dataset is missing required columns: " + ", ".join(missing_columns)
        )


def build_model() -> Sequential:
    """Build the prototype LSTM model."""

    model = Sequential(
        [
            LSTM(
                64,
                input_shape=(TIMESTEPS, FEATURES_PER_TIMESTEP),
                name="phase_sequence_lstm",
            ),
            Dropout(0.2, name="dropout"),
            Dense(32, activation="relu", name="dense_relu"),
            Dense(1, name="total_duration_output"),
        ]
    )
    model.compile(optimizer="adam", loss="mean_squared_error")
    return model


def main() -> None:
    """Load data, train LSTM, evaluate, and save model/scalers."""

    if not DATASET_PATH.exists():
        raise FileNotFoundError(
            f"Dataset not found: {DATASET_PATH}. "
            "Run app/training/generate_synthetic_dataset.py first."
        )

    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(DATASET_PATH)
    validate_columns(df)

    X_raw = df[PHASE_DURATION_COLUMNS].values.astype(float)
    y_raw = df[[TARGET_COLUMN]].values.astype(float)

    x_scaler = MinMaxScaler()
    y_scaler = MinMaxScaler()

    X_scaled = x_scaler.fit_transform(X_raw)
    y_scaled = y_scaler.fit_transform(y_raw)

    X_lstm = X_scaled.reshape(-1, TIMESTEPS, FEATURES_PER_TIMESTEP)

    X_train, X_test, y_train, y_test = train_test_split(
        X_lstm,
        y_scaled,
        test_size=0.2,
        random_state=42,
    )

    model = build_model()

    print("Training LSTM timeline model...")
    history = model.fit(
        X_train,
        y_train,
        epochs=50,
        batch_size=32,
        validation_split=0.2,
        verbose=1,
    )

    y_pred_scaled = model.predict(X_test, verbose=0)
    y_pred = y_scaler.inverse_transform(y_pred_scaled)
    y_test_actual = y_scaler.inverse_transform(y_test)

    mae = mean_absolute_error(y_test_actual, y_pred)
    r2 = r2_score(y_test_actual, y_pred)

    model.save(MODEL_PATH)
    joblib.dump(x_scaler, X_SCALER_PATH)
    joblib.dump(y_scaler, Y_SCALER_PATH)

    print("\nLSTM Training Completed")
    print("=" * 50)
    print(f"Dataset size       : {len(df)} records")
    print(f"Input shape        : {X_lstm.shape}")
    print(f"Train size         : {len(X_train)} records")
    print(f"Test size          : {len(X_test)} records")
    print(f"MAE                : {mae:.4f} days")
    print(f"R2 score           : {r2:.4f}")
    print(f"Saved model path   : {MODEL_PATH}")
    print(f"Saved X scaler     : {X_SCALER_PATH}")
    print(f"Saved y scaler     : {Y_SCALER_PATH}")
    print(f"Final train loss   : {history.history['loss'][-1]:.6f}")
    print(f"Final val loss     : {history.history['val_loss'][-1]:.6f}")


if __name__ == "__main__":
    main()
