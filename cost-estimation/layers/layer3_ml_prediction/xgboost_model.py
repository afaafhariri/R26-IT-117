"""XGBoost cost prediction with conformally-calibrated prediction intervals.

Models maintained:
  - point model            (objective: reg:squarederror, trained on log-cost)
  - quantile models        (objective: reg:quantileerror) at alpha 0.05, 0.25, 0.75,
                            0.90, 0.95

Raw quantile regression is badly miscalibrated on this data: 500 trees at depth 6 fit
the conditional quantiles of a near-deterministic generator almost exactly, so the
out-of-sample interval is far too tight (a 90% nominal band achieved 51% empirical
coverage). Conformalized Quantile Regression (Romano, Patterson & Candes, 2019) fixes
this: the quantile models are fitted on a proper-training subset, and a held-out
calibration subset supplies an additive offset Q in log space that is applied to the
raw quantiles at inference:

    two-sided:  [ q_lo(x) - Q ,  q_hi(x) + Q ]
    one-sided:  q_a(x) + Q

Q is the ceil((n+1)*level)/n empirical quantile of the conformity scores, which gives a
distribution-free finite-sample coverage guarantee independent of the model or the data
distribution.

IMPORTANT: the offsets are only valid for the models they were computed with. Any
retraining, or any change to the training data, requires recomputing them — a stale
offset silently voids the guarantee and raises no error.
"""

import json
import logging
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import xgboost as xgb

logger = logging.getLogger(__name__)

_MODELS_DIR = Path(__file__).parent.parent.parent / "models"
_OFFSETS_FILE = "conformal_offsets.json"

# Quantiles trained. 0.25/0.75 back the default displayed band, 0.05/0.95 the wider
# 90% band, 0.90 the one-sided budget figure.
QUANTILE_ALPHAS: tuple[float, ...] = (0.05, 0.25, 0.75, 0.90, 0.95)

# Displayed by default. A conformalized 50% band is narrow enough to be actionable and
# is honestly labelled; the 90% band is retained but is roughly three times as wide.
DEFAULT_INTERVAL_LEVEL = 0.50
DEFAULT_BUDGET_LEVEL = 0.90

# Fraction of the training set held out to calibrate the conformal offsets.
DEFAULT_CALIBRATION_FRAC = 0.35

# Below this many calibration rows the empirical quantile is too coarse to be meaningful.
_MIN_CALIBRATION_ROWS = 10

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


def _alpha_key(alpha: float) -> str:
    """Filename-safe key for a quantile level: 0.05 -> 'q05', 0.9 -> 'q90'."""
    return f"q{int(round(alpha * 100)):02d}"


def _band_alphas(level: float) -> tuple[float, float]:
    """Lower/upper quantile alphas for a two-sided interval at `level`."""
    tail = (1.0 - level) / 2.0
    return round(tail, 4), round(1.0 - tail, 4)


def _conformal_quantile(scores: np.ndarray, level: float) -> float:
    """Finite-sample-corrected empirical quantile of the conformity scores."""
    n = len(scores)
    k = int(np.ceil((n + 1) * level))
    if k > n:  # requested level unreachable with this many calibration points
        logger.warning(
            "Calibration set of %d rows cannot support level %.2f — using the maximum "
            "score, so realised coverage may fall short.", n, level,
        )
        k = n
    return float(np.sort(scores)[k - 1])


class XGBoostCostModel:
    """XGBoost point estimate plus conformally-calibrated quantile intervals."""

    def __init__(self) -> None:
        self._point_model: Optional[xgb.XGBRegressor] = None
        self._quantile_models: dict[float, xgb.XGBRegressor] = {}
        self._conformal: dict[str, float] = {}

    # ------------------------------------------------------------------
    # Training
    # ------------------------------------------------------------------

    def train(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        calibration_frac: float = DEFAULT_CALIBRATION_FRAC,
        random_state: int = 42,
    ) -> None:
        """Fit the point model, the quantile models, and the conformal offsets.

        The point model uses all supplied rows. The quantile models are fitted on a
        proper-training subset only; the remaining `calibration_frac` is held out to
        compute the conformal offsets, which is what makes the coverage guarantee valid.

        Args:
            X: Feature DataFrame from FeatureEngineer.build_features().
            y: Series of project costs in LKR.
            calibration_frac: Fraction of rows reserved for conformal calibration.
            random_state: Seed for the proper-train/calibration split.
        """
        from sklearn.model_selection import train_test_split

        log_y = np.log1p(np.asarray(y, dtype=float))

        logger.info("Training XGBoost point model on %d samples.", len(X))
        self._point_model = xgb.XGBRegressor(objective="reg:squarederror", **_BASE_PARAMS)
        self._point_model.fit(X, log_y, verbose=False)

        n_cal = int(len(X) * calibration_frac)
        if n_cal < _MIN_CALIBRATION_ROWS:
            logger.warning(
                "Only %d rows would be available for calibration (< %d). Fitting quantile "
                "models on all data and setting conformal offsets to zero — intervals will "
                "NOT carry a coverage guarantee.", n_cal, _MIN_CALIBRATION_ROWS,
            )
            X_proper, log_y_proper = X, log_y
            X_cal = log_y_cal = None
        else:
            X_proper, X_cal, log_y_proper, log_y_cal = train_test_split(
                X, log_y, test_size=calibration_frac, random_state=random_state
            )
            logger.info(
                "Proper-train %d rows / calibration %d rows.", len(X_proper), len(X_cal)
            )

        self._quantile_models = {}
        for alpha in QUANTILE_ALPHAS:
            logger.info("Training quantile model alpha=%.2f.", alpha)
            model = xgb.XGBRegressor(
                objective="reg:quantileerror", quantile_alpha=alpha, **_BASE_PARAMS
            )
            model.fit(X_proper, log_y_proper, verbose=False)
            self._quantile_models[alpha] = model

        self._conformal = {}
        if X_cal is not None:
            self._calibrate(X_cal, log_y_cal)
        logger.info("XGBoost training complete. Offsets: %s", self._conformal)

    def _calibrate(self, X_cal: pd.DataFrame, log_y_cal: np.ndarray) -> None:
        """Compute conformal offsets from held-out calibration data."""
        # Two-sided bands
        for level in (0.50, 0.90):
            a_lo, a_hi = _band_alphas(level)
            lo = self._quantile_models[a_lo].predict(X_cal)
            hi = self._quantile_models[a_hi].predict(X_cal)
            scores = np.maximum(lo - log_y_cal, log_y_cal - hi)
            self._conformal[f"band_{level:.2f}"] = _conformal_quantile(scores, level)

        # One-sided upper bound (budget figure)
        a = DEFAULT_BUDGET_LEVEL
        scores = log_y_cal - self._quantile_models[a].predict(X_cal)
        self._conformal[f"upper_{a:.2f}"] = _conformal_quantile(scores, a)

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------

    def predict(self, X: pd.DataFrame) -> float:
        """Return the point cost estimate in LKR."""
        if self._point_model is None:
            logger.warning("XGBoost point model not loaded — returning 0.")
            return 0.0
        return float(np.expm1(float(self._point_model.predict(X)[0])))

    def predict_interval(
        self, X: pd.DataFrame, level: float = DEFAULT_INTERVAL_LEVEL
    ) -> tuple[float, float]:
        """Return the conformalized two-sided interval (lower_lkr, upper_lkr).

        Args:
            X: Single-row feature DataFrame.
            level: Nominal coverage, 0.50 or 0.90.

        Returns:
            (lower, upper) in LKR, or (0.0, 0.0) if the models are unavailable.
        """
        a_lo, a_hi = _band_alphas(level)
        lo_model = self._quantile_models.get(a_lo)
        hi_model = self._quantile_models.get(a_hi)
        if lo_model is None or hi_model is None:
            logger.warning("Quantile models for level %.2f not loaded — returning (0, 0).", level)
            return (0.0, 0.0)

        q = self._conformal.get(f"band_{level:.2f}", 0.0)
        lower = float(np.expm1(float(lo_model.predict(X)[0]) - q))
        upper = float(np.expm1(float(hi_model.predict(X)[0]) + q))
        return (max(0.0, lower), upper)

    def predict_budget(
        self, X: pd.DataFrame, level: float = DEFAULT_BUDGET_LEVEL
    ) -> float:
        """Return a one-sided upper bound: `level` of comparable projects fall at or below it.

        Returns 0.0 if the required quantile model is unavailable.
        """
        model = self._quantile_models.get(level)
        if model is None:
            logger.warning("Quantile model alpha=%.2f not loaded — returning 0.", level)
            return 0.0
        q = self._conformal.get(f"upper_{level:.2f}", 0.0)
        return float(np.expm1(float(model.predict(X)[0]) + q))

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, path: Optional[str] = None) -> None:
        """Save the point model, every quantile model, and the conformal offsets."""
        models_dir = Path(path) if path else _MODELS_DIR
        models_dir.mkdir(parents=True, exist_ok=True)

        if self._point_model:
            self._point_model.save_model(str(models_dir / "xgboost_point.json"))
        for alpha, model in self._quantile_models.items():
            model.save_model(str(models_dir / f"xgboost_{_alpha_key(alpha)}.json"))
        (models_dir / _OFFSETS_FILE).write_text(json.dumps(self._conformal, indent=2))
        logger.info("Saved %d models + offsets to %s.",
                    1 + len(self._quantile_models), models_dir)

    def load(self, path: Optional[str] = None) -> None:
        """Load the point model, quantile models, and conformal offsets."""
        models_dir = Path(path) if path else _MODELS_DIR

        point_path = models_dir / "xgboost_point.json"
        if point_path.exists():
            self._point_model = xgb.XGBRegressor()
            self._point_model.load_model(str(point_path))
            logger.info("Loaded XGBoost point model from %s.", point_path)
        else:
            logger.warning("Point model file not found at %s.", point_path)

        # Legacy filenames from the pre-conformal layout, so an old models/ directory
        # still yields a usable (uncalibrated) 90% band.
        legacy = {0.05: "xgboost_p5.json", 0.95: "xgboost_p95.json"}
        self._quantile_models = {}
        for alpha in QUANTILE_ALPHAS:
            p = models_dir / f"xgboost_{_alpha_key(alpha)}.json"
            if not p.exists() and alpha in legacy:
                p = models_dir / legacy[alpha]
            if p.exists():
                model = xgb.XGBRegressor()
                model.load_model(str(p))
                self._quantile_models[alpha] = model

        offsets_path = models_dir / _OFFSETS_FILE
        if offsets_path.exists():
            self._conformal = {k: float(v) for k, v in
                               json.loads(offsets_path.read_text()).items()}
        else:
            self._conformal = {}
            if self._quantile_models:
                logger.warning(
                    "No %s in %s — intervals will be returned UNCALIBRATED and will "
                    "under-cover. Re-run scripts/train_model.py.", _OFFSETS_FILE, models_dir,
                )

    @property
    def is_loaded(self) -> bool:
        """True if at least the point model is ready for inference."""
        return self._point_model is not None

    @property
    def is_calibrated(self) -> bool:
        """True if conformal offsets are available for the default interval level."""
        return f"band_{DEFAULT_INTERVAL_LEVEL:.2f}" in self._conformal
