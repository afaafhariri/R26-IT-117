"""
Train a PyTorch LSTM model for construction timeline prediction.

This script avoids TensorFlow entirely. It uses phase duration sequences to
learn construction schedule patterns and predict total project duration.
"""

from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import torch
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import MinMaxScaler
from torch import nn
from torch.utils.data import DataLoader, TensorDataset


BASE_DIR = Path(__file__).resolve().parents[2]
DATASET_PATH = BASE_DIR / "data" / "residential_timeline_dataset.csv"
MODELS_DIR = BASE_DIR / "models"
MODEL_PATH = MODELS_DIR / "timeline_lstm_pytorch.pt"
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

EPOCHS = 100
BATCH_SIZE = 32
LEARNING_RATE = 0.001
RANDOM_STATE = 42


class ConstructionLSTM(nn.Module):
    """PyTorch LSTM model for construction phase sequence prediction."""

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
    """Check whether all required phase sequence and target columns exist."""

    required_columns = PHASE_DURATION_COLUMNS + [TARGET_COLUMN]
    missing_columns = [column for column in required_columns if column not in df.columns]
    if missing_columns:
        raise ValueError(
            "Dataset is missing required columns: " + ", ".join(missing_columns)
        )


def set_random_seed(seed: int = RANDOM_STATE) -> None:
    """Make training results more reproducible."""

    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def main() -> None:
    """Load dataset, train PyTorch LSTM, evaluate, and save artifacts."""

    if not DATASET_PATH.exists():
        raise FileNotFoundError(
            f"Dataset not found: {DATASET_PATH}. "
            "Run app/training/generate_synthetic_dataset.py first."
        )

    set_random_seed()
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(DATASET_PATH)
    validate_columns(df)

    X_raw = df[PHASE_DURATION_COLUMNS].values.astype(np.float32)
    y_raw = df[[TARGET_COLUMN]].values.astype(np.float32)

    x_scaler = MinMaxScaler()
    y_scaler = MinMaxScaler()

    X_scaled = x_scaler.fit_transform(X_raw).astype(np.float32)
    y_scaled = y_scaler.fit_transform(y_raw).astype(np.float32)

    X_lstm = X_scaled.reshape(-1, TIMESTEPS, FEATURES_PER_TIMESTEP)

    X_train, X_test, y_train, y_test = train_test_split(
        X_lstm,
        y_scaled,
        test_size=0.2,
        random_state=RANDOM_STATE,
    )

    train_dataset = TensorDataset(
        torch.tensor(X_train, dtype=torch.float32),
        torch.tensor(y_train, dtype=torch.float32),
    )
    train_loader = DataLoader(
        train_dataset,
        batch_size=BATCH_SIZE,
        shuffle=True,
    )

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = ConstructionLSTM().to(device)
    criterion = nn.MSELoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=LEARNING_RATE)

    print("Training PyTorch LSTM timeline model...")
    print(f"Device             : {device}")

    model.train()
    for epoch in range(1, EPOCHS + 1):
        epoch_loss = 0.0
        for batch_X, batch_y in train_loader:
            batch_X = batch_X.to(device)
            batch_y = batch_y.to(device)

            optimizer.zero_grad()
            outputs = model(batch_X)
            loss = criterion(outputs, batch_y)
            loss.backward()
            optimizer.step()

            epoch_loss += loss.item() * batch_X.size(0)

        avg_loss = epoch_loss / len(train_loader.dataset)
        if epoch == 1 or epoch % 10 == 0 or epoch == EPOCHS:
            print(f"Epoch {epoch:3d}/{EPOCHS} - loss: {avg_loss:.6f}")

    model.eval()
    with torch.no_grad():
        X_test_tensor = torch.tensor(X_test, dtype=torch.float32).to(device)
        y_pred_scaled = model(X_test_tensor).cpu().numpy()

    y_pred = y_scaler.inverse_transform(y_pred_scaled)
    y_test_actual = y_scaler.inverse_transform(y_test)

    mae = mean_absolute_error(y_test_actual, y_pred)
    r2 = r2_score(y_test_actual, y_pred)

    torch.save(
        {
            "model_state_dict": model.state_dict(),
            "input_size": FEATURES_PER_TIMESTEP,
            "hidden_size": 64,
            "num_layers": 1,
            "phase_duration_columns": PHASE_DURATION_COLUMNS,
            "target_column": TARGET_COLUMN,
            "timesteps": TIMESTEPS,
            "mae": mae,
            "r2_score": r2,
        },
        MODEL_PATH,
    )
    joblib.dump(x_scaler, X_SCALER_PATH)
    joblib.dump(y_scaler, Y_SCALER_PATH)

    print("\nPyTorch LSTM Training Completed")
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


if __name__ == "__main__":
    main()
