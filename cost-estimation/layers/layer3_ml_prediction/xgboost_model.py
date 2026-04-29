"""XGBoost cost prediction model — point estimate and 90% prediction interval.

Three model instances are maintained:
  - point model (objective: reg:squarederror, trained on log-cost)
  - lower quantile model (alpha=0.05, objective: reg:quantileerror)
  - upper quantile model (alpha=0.95, objective: reg:quantileerror)
"""

import logging
import os
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import xgboost as xgb

logger = logging.getLogger(__name__)

_MODELS_DIR = Path(__file__).parent.parent.parent / "models"

_BASE_PARAMS: dict = {
    "n_estimators": 500,
    "max_depth": 6,
    "learning_rate": 0.05,
    "reg_alpha": 0.1,
    "reg_lambda": 1.0,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "random_state": 42,
    "n_jobs": -1,
}


class XGBoostCostModel:
    """XGBoost wrapper with point + quantile regression for 90% prediction intervals."""

    def __init__(self) -> None:
        self._point_model: Optional[xgb.XGBRegressor] = None
        self._lower_model: Optional[xgb.XGBRegressor] = None
        self._upper_model: Optional[xgb.XGBRegressor] = None

    # ------------------------------------------------------------------
    # Training
    # ------------------------------------------------------------------

    def train(self, X: pd.DataFrame, y: pd.Series) -> None:
        """Train point estimate and quantile models on log-transformed cost.

        Args:
            X: Feature DataFrame from FeatureEngineer.build_features().
            y: Series of actual project costs in LKR.
        """
        log_y = np.log1p(y)

        logger.info("Training XGBoost point model on %d samples.", len(X))
        self._point_model = xgb.XGBRegressor(
            objective="reg:squarederror", **_BASE_PARAMS
        )
        self._point_model.fit(X, log_y, eval_set=[(X, log_y)], verbose=False)

        logger.info("Training XGBoost lower-quantile model (alpha=0.05).")
        self._lower_model = xgb.XGBRegressor(
            objective="reg:quantileerror",
            quantile_alpha=0.05,
            **_BASE_PARAMS,
        )
        self._lower_model.fit(X, log_y, eval_set=[(X, log_y)], verbose=False)

        logger.info("Training XGBoost upper-quantile model (alpha=0.95).")
        self._upper_model = xgb.XGBRegressor(
            objective="reg:quantileerror",
            quantile_alpha=0.95,
            **_BASE_PARAMS,
        )
        self._upper_model.fit(X, log_y, eval_set=[(X, log_y)], verbose=False)
        logger.info("XGBoost training complete.")

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------

    def predict(self, X: pd.DataFrame) -> float:
        """Return point cost estimate in LKR (exponentiated from log-space).

        Args:
            X: Single-row feature DataFrame.

        Returns:
            Predicted cost in LKR.
        """
        if self._point_model is None:
            logger.warning("XGBoost point model not loaded — returning 0.")
            return 0.0
        log_pred = float(self._point_model.predict(X)[0])
        return float(np.expm1(log_pred))

    def predict_interval(self, X: pd.DataFrame) -> tuple[float, float]:
        """Return the 90% prediction interval (lower_lkr, upper_lkr).

        Args:
            X: Single-row feature DataFrame.

        Returns:
            Tuple of (5th-percentile cost, 95th-percentile cost) in LKR.
        """
        if self._lower_model is None or self._upper_model is None:
            logger.warning("XGBoost quantile models not loaded — returning (0, 0).")
            return (0.0, 0.0)
        lower_log = float(self._lower_model.predict(X)[0])
        upper_log = float(self._upper_model.predict(X)[0])
        return (float(np.expm1(lower_log)), float(np.expm1(upper_log)))

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, path: Optional[str] = None) -> None:
        """Save all three model JSON files to the models directory.

        Args:
            path: Directory path. Defaults to /component02/models/.
        """
        models_dir = Path(path) if path else _MODELS_DIR
        models_dir.mkdir(parents=True, exist_ok=True)

        if self._point_model:
            self._point_model.save_model(str(models_dir / "xgboost_point.json"))
        if self._lower_model:
            self._lower_model.save_model(str(models_dir / "xgboost_p5.json"))
        if self._upper_model:
            self._upper_model.save_model(str(models_dir / "xgboost_p95.json"))
        logger.info("XGBoost models saved to %s.", models_dir)

    def load(self, path: Optional[str] = None) -> None:
        """Load model JSON files from the models directory.

        Args:
            path: Directory path. Defaults to /component02/models/.
        """
        models_dir = Path(path) if path else _MODELS_DIR

        point_path = models_dir / "xgboost_point.json"
        lower_path = models_dir / "xgboost_p5.json"
        upper_path = models_dir / "xgboost_p95.json"

        if point_path.exists():
            self._point_model = xgb.XGBRegressor()
            self._point_model.load_model(str(point_path))
            logger.info("Loaded XGBoost point model from %s.", point_path)
        else:
            logger.warning("Point model file not found at %s.", point_path)

        if lower_path.exists():
            self._lower_model = xgb.XGBRegressor()
            self._lower_model.load_model(str(lower_path))

        if upper_path.exists():
            self._upper_model = xgb.XGBRegressor()
            self._upper_model.load_model(str(upper_path))

    @property
    def is_loaded(self) -> bool:
        """True if at least the point model is ready for inference."""
        return self._point_model is not None
