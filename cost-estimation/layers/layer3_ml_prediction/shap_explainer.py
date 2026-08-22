"""SHAP-based model explainability — surfaces the top cost drivers in plain English."""

import logging
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Maps internal feature names to human-readable English labels
_FEATURE_LABELS: dict[str, str] = {
    "concrete_m3": "total concrete volume",
    "steel_kg": "reinforcement steel weight",
    "brickwork_m3": "total masonry volume",
    "floor_area_sqm": "total floor area",
    "wall_plaster_sqm": "wall plaster area",
    "door_count": "number of doors",
    "window_count": "number of windows",
    "bathroom_count": "number of bathrooms",
    "concrete_per_sqm": "concrete intensity per square metre",
    "steel_to_concrete_ratio": "steel-to-concrete ratio",
    "opening_to_wall_ratio": "openings-to-wall ratio",
    "perimeter_to_area_ratio": "perimeter-to-area ratio",
    "is_coastal": "coastal site surcharge",
    "terrain_encoded": "site terrain difficulty",
    "road_access_encoded": "road access quality",
    "finish_grade_encoded": "finish specification grade",
    "roof_type_encoded": "roof type complexity",
    "floors": "number of building floors",
}


class SHAPExplainer:
    """Computes and formats SHAP values for XGBoost cost predictions."""

    def __init__(self, top_n: int = 5) -> None:
        self._top_n = top_n

    def explain(self, model, X: pd.DataFrame) -> list[dict]:
        """Return the top-N cost drivers with SHAP impact values in LKR.

        The SHAP values are computed in log-cost space and then converted to
        LKR impact by multiplying by the predicted cost (first-order approximation).

        Args:
            model: A fitted XGBoostCostModel instance.
            X: Single-row feature DataFrame from FeatureEngineer.build_features().

        Returns:
            List of up to top_n dicts:
              [{"feature": str, "impact_lkr": float, "direction": "increases"/"decreases"}, ...]
            Returns an empty list if SHAP cannot be computed.
        """
        try:
            import shap
        except ImportError:
            logger.error("shap package not installed — cannot explain predictions.")
            return []

        xgb_model = getattr(model, "_point_model", None)
        if xgb_model is None:
            logger.warning("XGBoost point model not available for SHAP explanation.")
            return []

        try:
            explainer = shap.TreeExplainer(xgb_model)
            shap_values = explainer.shap_values(X)

            # shap_values shape: (n_samples, n_features) — we have 1 sample
            shap_row = shap_values[0] if shap_values.ndim == 2 else shap_values

            # Predicted log-cost to convert SHAP (log-space) to LKR impact
            log_pred = float(xgb_model.predict(X)[0])
            predicted_cost_lkr = float(np.expm1(log_pred))

            feature_names = list(X.columns)
            impacts = []
            for fname, sv in zip(feature_names, shap_row):
                # Approximate LKR impact: d(exp(log_pred))/d(log_pred) ≈ exp(log_pred)
                impact_lkr = float(sv) * predicted_cost_lkr
                impacts.append((fname, impact_lkr))

            # Sort by absolute impact, descending
            impacts.sort(key=lambda t: abs(t[1]), reverse=True)
            top = impacts[: self._top_n]

            result = []
            for fname, impact_lkr in top:
                label = _FEATURE_LABELS.get(fname, fname.replace("_", " "))
                result.append(
                    {
                        "feature": label,
                        "impact_lkr": round(abs(impact_lkr), 2),
                        "direction": "increases" if impact_lkr > 0 else "decreases",
                    }
                )
            return result

        except Exception as exc:
            logger.error("SHAP explanation failed: %s", exc)
            return []

    def format_summary(self, explanations: list[dict]) -> str:
        """Return a plain-English summary string of the top drivers.

        Args:
            explanations: Output from explain().

        Returns:
            Human-readable cost driver summary.
        """
        if not explanations:
            return "No cost driver information available."
        lines = []
        for i, item in enumerate(explanations, start=1):
            direction = item["direction"]
            feature = item["feature"]
            impact = item["impact_lkr"]
            lines.append(
                f"{i}. {feature.capitalize()} {direction} the estimate "
                f"by approximately LKR {impact:,.0f}."
            )
        return "\n".join(lines)
