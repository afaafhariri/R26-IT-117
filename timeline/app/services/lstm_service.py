"""PyTorch LSTM total-duration prediction service.

TensorFlow is intentionally not imported here. The trained LSTM model was built
with PyTorch because TensorFlow failed to load in the Windows development
environment.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import torch
from torch import nn


logger = logging.getLogger(__name__)
BASE_DIR = Path(__file__).resolve().parents[2]
LSTM_MODEL_PATH = BASE_DIR / "models" / "timeline_lstm_pytorch.pt"
X_SCALER_PATH = BASE_DIR / "models" / "lstm_x_scaler.pkl"
Y_SCALER_PATH = BASE_DIR / "models" / "lstm_y_scaler.pkl"

PHASE_SEQUENCE_ORDER = [
    "foundation",
    "structure",
    "masonry",
    "roofing",
    "electrical",
    "plumbing",
    "plastering",
    "finishing",
    "painting",
    "external_work",
    "handover",
]


class ConstructionLSTM(nn.Module):
    """Runtime model definition matching the PyTorch training architecture."""

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


def predict_total_duration_with_lstm(
    phase_days: dict[str, int],
    scheduled_total_duration_days: int,
    scheduled_total_duration_weeks: float,
) -> dict[str, float | int | str]:
    """
    Predict total duration using the trained PyTorch LSTM model.

    If loading or prediction fails, the function safely returns the scheduled
    CPM/Gantt duration as the fallback value.
    """

    try:
        if not (
            LSTM_MODEL_PATH.exists()
            and X_SCALER_PATH.exists()
            and Y_SCALER_PATH.exists()
        ):
            raise FileNotFoundError("LSTM model or scaler file is missing")

        import joblib

        sequence = [
            max(1.0, float(phase_days[phase]))
            for phase in PHASE_SEQUENCE_ORDER
        ]

        x_scaler = joblib.load(X_SCALER_PATH)
        y_scaler = joblib.load(Y_SCALER_PATH)

        sequence_scaled = x_scaler.transform([sequence])
        sequence_lstm = sequence_scaled.reshape(1, len(PHASE_SEQUENCE_ORDER), 1)

        checkpoint = torch.load(
            LSTM_MODEL_PATH,
            map_location=torch.device("cpu"),
            weights_only=False,
        )

        model = ConstructionLSTM()
        model.load_state_dict(checkpoint["model_state_dict"])
        model.eval()

        with torch.no_grad():
            tensor_input = torch.tensor(sequence_lstm, dtype=torch.float32)
            scaled_prediction = model(tensor_input).numpy()

        predicted_days = float(y_scaler.inverse_transform(scaled_prediction)[0][0])
        predicted_days_int = max(1, int(round(predicted_days)))
        predicted_weeks = round(predicted_days_int / 7, 2)

        return {
            "lstm_predicted_total_duration_days": predicted_days_int,
            "lstm_predicted_total_duration_weeks": predicted_weeks,
            "lstm_status": "trained PyTorch LSTM model used",
        }

    except Exception as exc:
        logger.warning("PyTorch LSTM prediction failed: %s", exc)
        return {
            "lstm_predicted_total_duration_days": int(scheduled_total_duration_days),
            "lstm_predicted_total_duration_weeks": float(scheduled_total_duration_weeks),
            "lstm_status": "fallback - LSTM prediction failed",
        }


def predict_timeline_with_lstm_placeholder(
    phase_durations: dict[str, Any],
    project_features: Any,
) -> dict[str, float | int | str]:
    """
    Backward-compatible fallback for non-sequence/rule-based paths.

    This does not load PyTorch because rule-based predictions do not provide the
    11-phase sequence required by the trained LSTM.
    """

    _ = project_features
    total_days = phase_durations.get("total_project_duration_days")
    total_weeks = phase_durations.get("total_project_duration_weeks")

    if total_days is None and total_weeks is not None:
        total_days = int(round(float(total_weeks) * 7))
    if total_weeks is None and total_days is not None:
        total_weeks = round(float(total_days) / 7, 2)

    return {
        "lstm_predicted_total_duration_days": int(total_days or 0),
        "lstm_predicted_total_duration_weeks": float(total_weeks or 0),
        "lstm_status": "fallback - LSTM prediction failed",
    }
