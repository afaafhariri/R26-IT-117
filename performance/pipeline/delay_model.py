"""
Delay prediction models.

Two-model ensemble
------------------
XGBoost classifier  → delay_risk category (low / medium / high)
LSTM regressor      → predicted_delay_days (continuous)

SHAP is used to identify the primary driver of each prediction.

Model artefacts are loaded from the ``models/`` directory at first
use (lazy initialisation) so the FastAPI process starts without
blocking on large file loads.
"""

import logging
import os
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

MODELS_DIR = Path(__file__).resolve().parents[1] / "models"
XGBOOST_PATH = MODELS_DIR / "delay_xgboost.json"
LSTM_PATH = MODELS_DIR / "lstm_weights.h5"

RISK_LABELS = ["low", "medium", "high"]

# Feature columns consumed by the models (must match training schema)
XGB_FEATURES = [
    "spi",
    "cpi_proxy",
    "schedule_variance",
    "rolling_7day_progress_rate",
    "days_since_phase_start",
    "floors",
    "footprint_sqm",
    "structural_complexity_score",
    "total_labour_days",
    "phase_budget_consumed_pct",
    "cumulative_weather_delay_days",
    "rework_rate_per_100_labour_days",
    "phase_encoded",
]

LSTM_SEQUENCE_FEATURES = [
    "spi",
    "schedule_variance",
    "rolling_7day_progress_rate",
    "cumulative_weather_delay_days",
]
LSTM_SEQUENCE_LEN = 10   # look-back window (time steps)


class DelayPredictor:
    """
    Lazy-loading delay prediction ensemble.

    Call ``predict(features_df)`` — the models are loaded from disk on
    the first invocation and cached for subsequent calls.
    """

    def __init__(self) -> None:
        self._xgb_model = None
        self._lstm_model = None
        self._explainer = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def predict(self, features: pd.DataFrame) -> dict[str, Any]:
        """
        Run the full prediction ensemble on a feature DataFrame.

        Parameters
        ----------
        features : pd.DataFrame
            Output of ``FeatureEngineer.build_features``.

        Returns
        -------
        dict with keys:
            delay_risk          "low" | "medium" | "high"
            predicted_delay_days int
            confidence          float  (0–1, from XGB probability)
            primary_cause       str    (top SHAP feature)
        """
        if features.empty:
            logger.warning("predict() called with empty feature DataFrame — returning defaults")
            return self._default_prediction()

        self._lazy_load()

        # Use the latest row for the snapshot prediction
        latest = features.tail(1)

        delay_risk, confidence = self._classify_risk(latest)
        predicted_days = self._regress_days(features)
        primary_cause = self._explain(latest)

        return {
            "delay_risk": delay_risk,
            "predicted_delay_days": predicted_days,
            "confidence": round(float(confidence), 4),
            "primary_cause": primary_cause,
        }

    # ------------------------------------------------------------------
    # Private — model loading (lazy)
    # ------------------------------------------------------------------

    def _lazy_load(self) -> None:
        if self._xgb_model is None:
            self._xgb_model = self._load_xgboost()
        if self._lstm_model is None:
            self._lstm_model = self._load_lstm()
        if self._explainer is None and self._xgb_model is not None:
            self._explainer = self._build_explainer()

    def _load_xgboost(self):
        """Load the trained XGBoost classifier from disk."""
        try:
            import xgboost as xgb  # noqa: PLC0415
            model = xgb.XGBClassifier()
            if XGBOOST_PATH.exists():
                model.load_model(str(XGBOOST_PATH))
                logger.info("XGBoost model loaded from %s", XGBOOST_PATH)
            else:
                # TODO: train the model and save to models/delay_xgboost.json
                logger.warning("XGBoost model file not found at %s — using untrained placeholder", XGBOOST_PATH)
            return model
        except Exception as exc:
            logger.exception("Failed to load XGBoost model: %s", exc)
            return None

    def _load_lstm(self):
        """Load the trained Keras LSTM regressor from disk."""
        try:
            import tensorflow as tf  # noqa: PLC0415
            if LSTM_PATH.exists():
                model = tf.keras.models.load_model(str(LSTM_PATH))
                logger.info("LSTM model loaded from %s", LSTM_PATH)
                return model
            else:
                # TODO: train the LSTM and save weights to models/lstm_weights.h5
                logger.warning("LSTM weights file not found at %s — building untrained placeholder", LSTM_PATH)
                return self._build_placeholder_lstm()
        except Exception as exc:
            logger.exception("Failed to load LSTM model: %s", exc)
            return None

    @staticmethod
    def _build_placeholder_lstm():
        """
        Minimal LSTM for shape validation during development.
        Replace with the real trained model before production.
        """
        import tensorflow as tf  # noqa: PLC0415
        model = tf.keras.Sequential([
            tf.keras.layers.Input(shape=(LSTM_SEQUENCE_LEN, len(LSTM_SEQUENCE_FEATURES))),
            tf.keras.layers.LSTM(64, return_sequences=False),
            tf.keras.layers.Dense(32, activation="relu"),
            tf.keras.layers.Dense(1),
        ])
        model.compile(optimizer="adam", loss="mse")
        return model

    def _build_explainer(self):
        """Build a SHAP TreeExplainer for the XGBoost model."""
        try:
            import shap  # noqa: PLC0415
            explainer = shap.TreeExplainer(self._xgb_model)
            logger.info("SHAP explainer initialised")
            return explainer
        except Exception as exc:
            logger.warning("SHAP explainer unavailable: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Private — inference
    # ------------------------------------------------------------------

    def _classify_risk(self, latest_row: pd.DataFrame) -> tuple[str, float]:
        """XGBoost 3-class classification → (risk_label, confidence)."""
        if self._xgb_model is None:
            return "low", 0.0

        try:
            X = self._align_features(latest_row, XGB_FEATURES)
            proba = self._xgb_model.predict_proba(X)[0]
            risk_idx = int(np.argmax(proba))
            return RISK_LABELS[risk_idx], float(proba[risk_idx])
        except Exception as exc:
            logger.exception("XGBoost classification failed: %s", exc)
            return "low", 0.0

    def _regress_days(self, features: pd.DataFrame) -> int:
        """LSTM regression → integer days-behind prediction."""
        if self._lstm_model is None:
            return 0

        try:
            seq = self._build_lstm_sequence(features)
            if seq is None:
                return 0
            prediction = self._lstm_model.predict(seq, verbose=0)
            return max(0, int(round(float(prediction[0][0]))))
        except Exception as exc:
            logger.exception("LSTM regression failed: %s", exc)
            return 0

    def _explain(self, latest_row: pd.DataFrame) -> str:
        """Return the name of the feature with the highest SHAP value."""
        if self._explainer is None:
            return "unknown"

        try:
            X = self._align_features(latest_row, XGB_FEATURES)
            shap_values = self._explainer.shap_values(X)
            # For multi-class, pick the predicted class
            if isinstance(shap_values, list):
                proba = self._xgb_model.predict_proba(X)[0]
                cls_idx = int(np.argmax(proba))
                values = shap_values[cls_idx][0]
            else:
                values = shap_values[0]

            top_idx = int(np.argmax(np.abs(values)))
            return XGB_FEATURES[top_idx] if top_idx < len(XGB_FEATURES) else "unknown"
        except Exception as exc:
            logger.warning("SHAP explanation failed: %s", exc)
            return "unknown"

    # ------------------------------------------------------------------
    # Private — helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _align_features(df: pd.DataFrame, feature_cols: list[str]) -> pd.DataFrame:
        """
        Align a DataFrame to the expected feature columns, filling missing
        columns with 0.0 and dropping extras.
        """
        for col in feature_cols:
            if col not in df.columns:
                df = df.copy()
                df[col] = 0.0
        return df[feature_cols].fillna(0.0)

    def _build_lstm_sequence(self, features: pd.DataFrame) -> "np.ndarray | None":
        """
        Build an (1, LSTM_SEQUENCE_LEN, n_features) array from the
        most recent rows in *features*.
        """
        seq_cols = [c for c in LSTM_SEQUENCE_FEATURES if c in features.columns]
        if not seq_cols:
            return None

        arr = features[seq_cols].fillna(0.0).values
        # Pad with zeros if fewer rows than the required sequence length
        if len(arr) < LSTM_SEQUENCE_LEN:
            pad = np.zeros((LSTM_SEQUENCE_LEN - len(arr), len(seq_cols)))
            arr = np.vstack([pad, arr])
        else:
            arr = arr[-LSTM_SEQUENCE_LEN:]

        return arr[np.newaxis, :, :]   # shape: (1, seq_len, n_features)

    @staticmethod
    def _default_prediction() -> dict[str, Any]:
        return {
            "delay_risk": "low",
            "predicted_delay_days": 0,
            "confidence": 0.0,
            "primary_cause": "unknown",
        }
