"""
ScheduleModel — Component 04 Pipeline Step 3.

Predicts working-day durations for all 18 construction phases.
During development, stub rules derived from building area are used.
Once labelled training data is available, call ScheduleModel.train()
to fit one XGBoost model per phase, then save with save_models().
"""

import os
import logging
import pandas as pd
import xgboost as xgb

from timeline.pipeline import phases as p

logger = logging.getLogger(__name__)

# Default directory where phase models are persisted
_DEFAULT_MODEL_DIR = os.path.join(os.path.dirname(__file__), "..", "models")


class ScheduleModel:
    """
    One XGBoost regressor per phase.  predict_phase_durations() falls back to
    area-based stub rules when no trained model is loaded for a phase.
    """

    # Feature columns the XGBoost models expect
    FEATURE_COLUMNS: list[str] = [
        "floors", "footprint_sqm", "total_area_sqm", "perimeter_m",
        "area_per_floor", "finish_grade_encoded", "roof_type_encoded",
        "foundation_type_encoded", "has_basement", "roof_complexity",
        "is_coastal", "district_encoded",
        "total_labour_days", "labour_days_per_sqm",
        "structural_complexity_score",
        "cost_per_sqm", "material_to_labour_ratio",
    ]

    def __init__(self) -> None:
        # {phase_name: xgb.XGBRegressor}
        self._models: dict[str, xgb.XGBRegressor] = {}

    # ── Inference ─────────────────────────────────────────────────────────────

    def predict_phase_durations(self, features: pd.DataFrame) -> dict[str, int]:
        """
        Return working-day duration for every phase.

        Uses a trained XGBoost model when available; otherwise falls back to
        deterministic stub rules so the API returns sensible values before
        training data exists.

        Args:
            features: Single-row DataFrame output from FeatureEngineer.

        Returns:
            dict[str, int]: {phase_name: duration_working_days}
        """
        row = features.iloc[0]
        footprint   = float(row.get("footprint_sqm",  0))
        total_area  = float(row.get("total_area_sqm", 0))
        floors      = int(row.get("floors", 1))
        complexity  = float(row.get("structural_complexity_score", 1.0))

        # ── Stub heuristics (TODO: replace per-phase with trained model) ──────
        stub: dict[str, int] = {
            p.SITE_PREPARATION:        max(3,  int(footprint * 0.05)),
            p.FOUNDATION:              max(7,  int(footprint * 0.15 * complexity)),
            p.SUPERSTRUCTURE:          max(14, int(total_area * 0.25 * complexity)),
            p.BRICKWORK_AND_BLOCKWORK: max(10, int(total_area * 0.10)),
            p.ROOF_STRUCTURE:          max(5,  int(footprint * 0.10)),
            p.ROOF_COVERING:           max(3,  int(footprint * 0.05)),
            p.EXTERNAL_PLASTERING:     max(7,  int(total_area * 0.08)),
            p.INTERNAL_PLASTERING:     max(10, int(total_area * 0.12)),
            p.FLOOR_FINISHING:         max(7,  int(total_area * 0.10)),
            p.DOOR_AND_WINDOW_FIXING:  max(5,  int(total_area * 0.05)),
            p.ELECTRICAL_FIRST_FIX:    max(5,  int(total_area * 0.05)),
            p.PLUMBING_FIRST_FIX:      max(5,  int(total_area * 0.05)),
            p.CEILING:                 max(5,  int(footprint * 0.08)),
            p.PAINTING:                max(7,  int(total_area * 0.15)),
            p.ELECTRICAL_SECOND_FIX:   max(3,  int(total_area * 0.04)),
            p.PLUMBING_SECOND_FIX:     max(3,  int(total_area * 0.04)),
            p.EXTERNAL_WORKS:          max(5,  int(footprint * 0.10)),
            p.FINAL_INSPECTION:        max(2,  floors),
        }

        # Override with trained model prediction where a model exists
        if self._models:
            X = self._extract_feature_matrix(features)
            for phase, model in self._models.items():
                try:
                    pred = model.predict(X)[0]
                    stub[phase] = max(1, int(round(pred)))
                except Exception as exc:
                    logger.warning("Model prediction failed for %s: %s", phase, exc)

        return {phase: max(1, int(v)) for phase, v in stub.items()}

    # ── Training ──────────────────────────────────────────────────────────────

    def train(self, X: pd.DataFrame, y_phases: pd.DataFrame) -> None:
        """
        Train one XGBRegressor per phase and store in self._models.

        Args:
            X:        Feature matrix — one row per historical project.
            y_phases: Target matrix — one column per phase, values are
                      actual working-day durations from site records.

        Example::

            model.train(X_train, y_train)
            model.save_models()
        """
        # TODO: add cross-validation, early stopping, and hyperparameter search
        for phase in p.ALL_PHASES:
            if phase not in y_phases.columns:
                logger.warning("No training labels for phase '%s' — skipping.", phase)
                continue

            regressor = xgb.XGBRegressor(
                n_estimators=300,
                max_depth=6,
                learning_rate=0.05,
                subsample=0.8,
                colsample_bytree=0.8,
                objective="reg:squarederror",
                random_state=42,
                n_jobs=-1,
            )
            regressor.fit(X[self.FEATURE_COLUMNS], y_phases[phase])
            self._models[phase] = regressor
            logger.info("Trained model for phase '%s'.", phase)

    # ── Persistence ───────────────────────────────────────────────────────────

    def save_models(self, model_dir: str = _DEFAULT_MODEL_DIR) -> None:
        """
        Persist every trained phase model to <model_dir>/<phase>.json.
        """
        os.makedirs(model_dir, exist_ok=True)
        for phase, model in self._models.items():
            path = os.path.join(model_dir, f"{phase}.json")
            model.save_model(path)
            logger.info("Saved model for '%s' → %s", phase, path)

    def load_models(self, model_dir: str = _DEFAULT_MODEL_DIR) -> None:
        """
        Load all per-phase model files found in model_dir.
        Files must be named <phase_name>.json.
        """
        if not os.path.isdir(model_dir):
            logger.warning("Model directory not found: %s — using stub rules.", model_dir)
            return

        for phase in p.ALL_PHASES:
            path = os.path.join(model_dir, f"{phase}.json")
            if os.path.isfile(path):
                model = xgb.XGBRegressor()
                model.load_model(path)
                self._models[phase] = model
                logger.info("Loaded model for '%s' from %s", phase, path)

    # ── Private helpers ───────────────────────────────────────────────────────

    def _extract_feature_matrix(self, features: pd.DataFrame) -> pd.DataFrame:
        """Return only the columns that the XGBoost models were trained on."""
        available = [c for c in self.FEATURE_COLUMNS if c in features.columns]
        missing   = [c for c in self.FEATURE_COLUMNS if c not in features.columns]
        if missing:
            logger.warning("Feature columns missing at inference time: %s", missing)
        return features[available]
