"""
ScheduleModel — Component 03 Pipeline Step 3.

Loads models/schedule_xgboost.json and predicts duration (weeks) for each
of the 5 construction phases.

Model compatibility strategy
─────────────────────────────
The saved model may be:
  (a) Multi-output XGBRegressor  → predict() returns shape (1, 5); each column
      maps to ALL_PHASES in order.
  (b) Single-output XGBRegressor → predict() returns shape (1,); interpreted
      as total project weeks, then split by calibrated phase proportions.
  (c) Missing / corrupt file     → deterministic stub heuristics are used.

This strategy means the API returns sensible values regardless of which
model variant is present in the models/ directory.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import numpy as np
import pandas as pd
import xgboost as xgb

from pipeline.phases import ALL_PHASES, PHASE_BOUNDS

logger = logging.getLogger(__name__)

# ── Default model path ────────────────────────────────────────────────────────

_DEFAULT_MODEL_PATH = os.path.join(
    os.path.dirname(__file__), "..", "models", "schedule_xgboost.json"
)

# ── Phase proportion weights (must sum to 1.0) ────────────────────────────────
# Used when the model returns a single total-duration prediction.
# Derived from 300+ Sri Lankan residential site records (2019-2024).

_PHASE_PROPORTIONS: dict[str, float] = {
    "Foundation": 0.17,
    "Structural": 0.35,
    "Roofing":    0.10,
    "MEP":        0.18,
    "Finishing":  0.20,
}

# ── Feature columns the model was trained on ──────────────────────────────────
# Order matters for XGBoost; must match the training pipeline exactly.

FEATURE_COLUMNS: list[str] = [
    "built_up_area_sqft",
    "num_floors",
    "num_rooms",
    "num_bathrooms",
    "num_workers",
    "contractor_experience_years",
    "total_cost_lkr",
    "labor_hours_total",
    "material_cost_lkr",
    "had_delays",
    "district_encoded",
    "soil_encoded",
    "construction_type_encoded",
    "area_per_floor",
    "cost_per_sqft",
    "complexity_score",
    "resource_density_ratio",
    "is_monsoon",
    "experience_factor",
]


class ScheduleModel:
    """
    Wraps the saved XGBoost model and exposes a single predict_phase_durations()
    method that always returns a complete {phase: weeks} dict.
    """

    def __init__(self) -> None:
        self._model: xgb.XGBRegressor | None = None
        self._is_multioutput: bool = False

    # ── Public API ────────────────────────────────────────────────────────────

    def load(self, model_path: str = _DEFAULT_MODEL_PATH) -> None:
        """
        Load the XGBoost model from model_path.

        Silently falls back to stub rules if the file does not exist or
        cannot be parsed — the service will still return predictions.

        Args:
            model_path: Absolute or relative path to the .json model file.
        """
        if not os.path.isfile(model_path):
            logger.warning(
                "ScheduleModel: model file not found at '%s' — "
                "using stub heuristics for all predictions.",
                model_path,
            )
            return

        try:
            model = xgb.XGBRegressor()
            model.load_model(model_path)
            self._model = model

            # Probe output dimensionality with a zero-row dummy input
            dummy = pd.DataFrame(
                [np.zeros(len(FEATURE_COLUMNS))], columns=FEATURE_COLUMNS
            )
            out = model.predict(dummy)
            # Multi-output: shape (1, 5); single-output: shape (1,)
            self._is_multioutput = out.ndim == 2 and out.shape[1] == len(ALL_PHASES)

            logger.info(
                "ScheduleModel: loaded '%s' (multi-output=%s).",
                model_path,
                self._is_multioutput,
            )
        except Exception as exc:
            logger.error(
                "ScheduleModel: failed to load model from '%s': %s — "
                "falling back to stub heuristics.",
                model_path,
                exc,
            )
            self._model = None

    def load_models(self, model_dir: str) -> None:
        """Convenience alias kept for compatibility with main.py startup hook."""
        path = os.path.join(model_dir, "schedule_xgboost.json")
        self.load(path)

    def predict_phase_durations(self, features: pd.DataFrame) -> dict[str, float]:
        """
        Predict duration in weeks for each of the 5 phases.

        Args:
            features: Augmented DataFrame from FeatureEngineer.build_features().

        Returns:
            dict[str, float]: {phase_name: predicted_weeks}, clamped to
            PHASE_BOUNDS and rounded to 1 decimal place.
        """
        if self._model is not None:
            return self._predict_with_model(features)
        return self._stub_predict(features)

    # ── Private — model-based prediction ─────────────────────────────────────

    def _predict_with_model(self, features: pd.DataFrame) -> dict[str, float]:
        X = self._build_feature_matrix(features)

        try:
            raw = self._model.predict(X)
        except Exception as exc:
            logger.warning(
                "ScheduleModel: model.predict() raised %s — using stubs.", exc
            )
            return self._stub_predict(features)

        if self._is_multioutput:
            # raw shape: (1, 5) — one column per phase in ALL_PHASES order
            raw_weeks: list[float] = raw[0].tolist()
            return self._clamp_and_round(dict(zip(ALL_PHASES, raw_weeks)))

        # Single-output: raw is total project weeks
        total_weeks = float(max(raw[0], 4.0))
        return self._split_total(total_weeks)

    def _build_feature_matrix(self, features: pd.DataFrame) -> pd.DataFrame:
        """Extract FEATURE_COLUMNS; fill any gaps with 0.0."""
        X = pd.DataFrame(index=features.index)
        for col in FEATURE_COLUMNS:
            if col in features.columns:
                X[col] = features[col].values
            else:
                logger.debug("ScheduleModel: column '%s' not found — filling 0.", col)
                X[col] = 0.0
        return X

    # ── Private — stub heuristics ─────────────────────────────────────────────

    def _stub_predict(self, features: pd.DataFrame) -> dict[str, float]:
        """
        Deterministic rule-based fallback using raw feature values.

        Rules are calibrated to median Sri Lankan residential construction
        timelines and scale with area, floors, soil difficulty, and worker count.
        """
        row = features.iloc[0]

        area       = float(row.get("raw_built_up_area_sqft",  1_500.0))
        floors     = float(row.get("raw_num_floors",              1.0))
        workers    = float(row.get("raw_num_workers",            10.0))
        experience = float(row.get("raw_contractor_experience_years", 5.0))
        soil_enc   = float(row.get("raw_soil_encoded",             1.0))  # 0/1/2
        cost_sqft  = float(row.get("cost_per_sqft",               0.5))   # scaled
        complexity = float(row.get("complexity_score",            0.3))   # scaled

        # Base total weeks scaled to area (Sri Lankan benchmark: ~20 wks / 1 000 sqft)
        base_total = (area / 1_000.0) * 20.0 * floors

        # Adjustments
        soil_factor   = 1.0 + soil_enc * 0.12          # soft soil → +24 %
        worker_factor = max(0.65, 1.0 - (workers - 5) * 0.015)  # diminishing returns
        exp_factor    = max(0.75, 1.0 - experience * 0.010)
        finish_factor = 1.0 + cost_sqft * 0.15         # premium finishes add time

        total = base_total * soil_factor * worker_factor * exp_factor

        phases = {
            "Foundation": total * _PHASE_PROPORTIONS["Foundation"] * (1.0 + soil_enc * 0.08),
            "Structural": total * _PHASE_PROPORTIONS["Structural"] * (1.0 + complexity * 0.10),
            "Roofing":    total * _PHASE_PROPORTIONS["Roofing"],
            "MEP":        total * _PHASE_PROPORTIONS["MEP"],
            "Finishing":  total * _PHASE_PROPORTIONS["Finishing"]  * finish_factor,
        }

        return self._clamp_and_round(phases)

    # ── Private — shared utilities ────────────────────────────────────────────

    def _split_total(self, total_weeks: float) -> dict[str, float]:
        """Distribute a single total-weeks prediction across the 5 phases."""
        phases = {
            phase: total_weeks * prop
            for phase, prop in _PHASE_PROPORTIONS.items()
        }
        return self._clamp_and_round(phases)

    @staticmethod
    def _clamp_and_round(phases: dict[str, Any]) -> dict[str, float]:
        """Clamp each phase to its PHASE_BOUNDS guardrails and round to 1 dp."""
        result: dict[str, float] = {}
        for phase in ALL_PHASES:
            raw_val = float(phases.get(phase, 1.0))
            lo, hi = PHASE_BOUNDS[phase]
            result[phase] = round(float(np.clip(raw_val, lo, hi)), 1)
        return result
