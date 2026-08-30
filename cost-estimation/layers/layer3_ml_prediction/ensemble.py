"""XGBoost cost predictor with conformally-calibrated intervals.

Wraps XGBoostCostModel and exposes the shape the report builder expects.

Three uncertainty figures are returned, because one symmetric band cannot serve both
purposes a cost estimate has:

  - a narrow **likely range** (50% by default) — what a client reads as "the price"
  - a wider **90% band** — retained for analysis, roughly three times as wide
  - a one-sided **budget figure** — "90% of comparable projects come in at or below
    this", which is the number someone actually sets a budget against

All three are conformalized. See xgboost_model.py for the calibration method.
"""

import logging
from typing import Optional

import pandas as pd

from .xgboost_model import (
    XGBoostCostModel,
    DEFAULT_BUDGET_LEVEL,
    DEFAULT_INTERVAL_LEVEL,
)

logger = logging.getLogger(__name__)


class EnsembleCostPredictor:
    """XGBoost point estimate plus calibrated interval and budget figures.

    Args:
        xgboost_model: Pre-instantiated XGBoostCostModel. If None, a new instance
                       is created.
        auto_load: If True and no model supplied, attempt to load from disk on init.
        interval_level: Nominal coverage of the displayed band (0.50 or 0.90).
    """

    def __init__(
        self,
        xgboost_model: Optional[XGBoostCostModel] = None,
        auto_load: bool = True,
        interval_level: float = DEFAULT_INTERVAL_LEVEL,
    ) -> None:
        self._xgb = xgboost_model or XGBoostCostModel()
        self._interval_level = interval_level

        if auto_load and not self._xgb.is_loaded:
            try:
                self._xgb.load()
            except Exception as exc:
                logger.warning("Could not auto-load XGBoost model: %s", exc)

        if self._xgb.is_loaded and not self._xgb.is_calibrated:
            logger.warning(
                "Models loaded but conformal offsets are missing — reported intervals "
                "will under-cover their nominal level."
            )

    def predict(self, X: pd.DataFrame) -> dict:
        """Return the point estimate with calibrated uncertainty figures.

        Args:
            X: Single-row feature DataFrame from FeatureEngineer.build_features().

        Returns:
            Dict with keys:
              point_estimate_lkr   — XGBoost point estimate
              lower_bound_lkr      — lower bound of the displayed band
              upper_bound_lkr      — upper bound of the displayed band
              confidence_level     — nominal coverage of that band
              interval_90_lkr      — {lower, upper} for the wider 90% band
              budget_lkr           — one-sided 90% upper bound
              is_calibrated        — False if conformal offsets were unavailable
              xgboost_prediction   — same as point_estimate_lkr
              mlp_prediction       — 0.0 (model removed, key kept for compat)
        """
        if not self._xgb.is_loaded:
            logger.error("XGBoost model not loaded — returning zeros.")
            return {
                "point_estimate_lkr": 0.0,
                "lower_bound_lkr": 0.0,
                "upper_bound_lkr": 0.0,
                "confidence_level": self._interval_level,
                "interval_90_lkr": {"lower_lkr": 0.0, "upper_lkr": 0.0},
                "budget_lkr": 0.0,
                "is_calibrated": False,
                "xgboost_prediction": 0.0,
                "mlp_prediction": 0.0,
            }

        point = self._xgb.predict(X)
        lower, upper = self._xgb.predict_interval(X, level=self._interval_level)
        lo90, hi90 = self._xgb.predict_interval(X, level=0.90)
        budget = self._xgb.predict_budget(X, level=DEFAULT_BUDGET_LEVEL)

        logger.info(
            "XGBoost: %.0f LKR  [%.0f – %.0f @ %.0f%%]  budget(p%.0f) %.0f",
            point, lower, upper, self._interval_level * 100,
            DEFAULT_BUDGET_LEVEL * 100, budget,
        )

        return {
            "point_estimate_lkr": round(point, 2),
            "lower_bound_lkr": round(lower, 2),
            "upper_bound_lkr": round(upper, 2),
            "confidence_level": self._interval_level,
            "interval_90_lkr": {"lower_lkr": round(lo90, 2), "upper_lkr": round(hi90, 2)},
            "budget_lkr": round(budget, 2),
            "is_calibrated": self._xgb.is_calibrated,
            "xgboost_prediction": round(point, 2),
            "mlp_prediction": 0.0,
        }
