"""XGBoost-only cost predictor with 90% prediction interval.

Wraps XGBoostCostModel (point + p5 + p95) and exposes the same interface
the report builder expects so no downstream changes are needed.
"""

import logging
from pathlib import Path
from typing import Optional

import pandas as pd

from .xgboost_model import XGBoostCostModel

logger = logging.getLogger(__name__)


class EnsembleCostPredictor:
    """XGBoost point estimate + quantile interval predictor.

    Args:
        xgboost_model: Pre-instantiated XGBoostCostModel. If None, a new
                       instance is created.
        auto_load: If True and no model supplied, attempt to load from disk
                   on init.
    """

    def __init__(
        self,
        xgboost_model: Optional[XGBoostCostModel] = None,
        mlp_model: Optional[object] = None,  # kept for call-site compat, unused
        auto_load: bool = True,
    ) -> None:
        self._xgb = xgboost_model or XGBoostCostModel()

        if auto_load and not self._xgb.is_loaded:
            try:
                self._xgb.load()
            except Exception as exc:
                logger.warning("Could not auto-load XGBoost model: %s", exc)

    def predict(self, X: pd.DataFrame) -> dict:
        """Return a cost prediction with 90% confidence interval.

        Args:
            X: Single-row feature DataFrame from FeatureEngineer.build_features().

        Returns:
            Dict with keys:
              point_estimate_lkr   — XGBoost point estimate
              lower_bound_lkr      — 5th-percentile (p5 model)
              upper_bound_lkr      — 95th-percentile (p95 model)
              xgboost_prediction   — same as point_estimate_lkr
              mlp_prediction       — 0.0 (model removed, key kept for compat)
              confidence_level     — 0.90
        """
        if not self._xgb.is_loaded:
            logger.error("XGBoost model not loaded — returning zeros.")
            return {
                "point_estimate_lkr": 0.0,
                "lower_bound_lkr": 0.0,
                "upper_bound_lkr": 0.0,
                "xgboost_prediction": 0.0,
                "mlp_prediction": 0.0,
                "confidence_level": 0.90,
            }

        point = self._xgb.predict(X)
        lower, upper = self._xgb.predict_interval(X)

        logger.info("XGBoost prediction: %.0f LKR  [%.0f – %.0f]", point, lower, upper)

        return {
            "point_estimate_lkr": round(point, 2),
            "lower_bound_lkr": round(lower, 2),
            "upper_bound_lkr": round(upper, 2),
            "xgboost_prediction": round(point, 2),
            "mlp_prediction": 0.0,
            "confidence_level": 0.90,
        }
