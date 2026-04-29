"""Ensemble predictor — weighted blend of XGBoost (65%) and Residual MLP (35%).

Both models predict log(cost); predictions are exponentiated before blending
so the ensemble operates in the original LKR space for interpretability.
"""

import logging
from pathlib import Path
from typing import Optional

import pandas as pd

from .xgboost_model import XGBoostCostModel
from .mlp_model import ResidualMLPModel

logger = logging.getLogger(__name__)

# Ensemble weights (must sum to 1.0)
XGBOOST_WEIGHT: float = 0.65
MLP_WEIGHT: float = 0.35


class EnsembleCostPredictor:
    """Blends XGBoost and MLP predictions with fixed weights.

    Args:
        xgboost_model: Pre-instantiated XGBoostCostModel (loaded or trained).
        mlp_model: Pre-instantiated ResidualMLPModel (loaded or trained).
        auto_load: If True and no models supplied, attempt to load from disk on init.
    """

    def __init__(
        self,
        xgboost_model: Optional[XGBoostCostModel] = None,
        mlp_model: Optional[ResidualMLPModel] = None,
        auto_load: bool = True,
    ) -> None:
        self._xgb = xgboost_model or XGBoostCostModel()
        self._mlp = mlp_model or ResidualMLPModel()

        if auto_load:
            if not self._xgb.is_loaded:
                try:
                    self._xgb.load()
                except Exception as exc:
                    logger.warning("Could not auto-load XGBoost model: %s", exc)
            if not self._mlp.is_loaded:
                try:
                    self._mlp.load()
                except Exception as exc:
                    logger.warning("Could not auto-load MLP model: %s", exc)

    def predict(self, X: pd.DataFrame) -> dict:
        """Return a blended cost prediction with 90% confidence interval.

        Behaviour when a model is not loaded:
          - Falls back to the available model with weight 1.0.
          - If neither model is loaded the ensemble returns zeros and logs a warning.

        Args:
            X: Single-row feature DataFrame from FeatureEngineer.build_features().

        Returns:
            Dict with keys:
              point_estimate_lkr   — weighted blended point estimate
              lower_bound_lkr      — 5th-percentile from XGBoost quantile model
              upper_bound_lkr      — 95th-percentile from XGBoost quantile model
              xgboost_prediction   — raw XGBoost point estimate
              mlp_prediction       — raw MLP point estimate
              confidence_level     — always 0.90
        """
        xgb_loaded = self._xgb.is_loaded
        mlp_loaded = self._mlp.is_loaded

        if not xgb_loaded and not mlp_loaded:
            logger.error("No models loaded — ensemble returning zeros.")
            return {
                "point_estimate_lkr": 0.0,
                "lower_bound_lkr": 0.0,
                "upper_bound_lkr": 0.0,
                "xgboost_prediction": 0.0,
                "mlp_prediction": 0.0,
                "confidence_level": 0.90,
            }

        xgb_pred = self._xgb.predict(X) if xgb_loaded else 0.0
        mlp_pred = self._mlp.predict(X) if mlp_loaded else 0.0
        lower, upper = self._xgb.predict_interval(X) if xgb_loaded else (0.0, 0.0)

        # Adjust weights if only one model is available
        if xgb_loaded and not mlp_loaded:
            w_xgb, w_mlp = 1.0, 0.0
        elif mlp_loaded and not xgb_loaded:
            w_xgb, w_mlp = 0.0, 1.0
        else:
            w_xgb, w_mlp = XGBOOST_WEIGHT, MLP_WEIGHT

        point_estimate = w_xgb * xgb_pred + w_mlp * mlp_pred

        logger.info(
            "Ensemble: xgb=%.0f (w=%.2f) mlp=%.0f (w=%.2f) -> %.0f LKR",
            xgb_pred, w_xgb, mlp_pred, w_mlp, point_estimate,
        )

        return {
            "point_estimate_lkr": round(point_estimate, 2),
            "lower_bound_lkr": round(lower, 2),
            "upper_bound_lkr": round(upper, 2),
            "xgboost_prediction": round(xgb_pred, 2),
            "mlp_prediction": round(mlp_pred, 2),
            "confidence_level": 0.90,
        }
