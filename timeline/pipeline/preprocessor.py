"""
Preprocessor — Component 04 Pipeline Step 1.

Extracts raw fields from the Building Schema JSON (Component 01)
and the Cost Report JSON (Component 02), applies categorical encoding,
and returns a clean single-row pandas DataFrame ready for feature
engineering.
"""

import pandas as pd


# ── Encoding look-up tables ───────────────────────────────────────────────────

_FINISH_GRADE_MAP: dict[str, int] = {
    "basic":    0,
    "standard": 1,
    "premium":  2,
}

_ROOF_TYPE_MAP: dict[str, int] = {
    "flat":    0,
    "pitched": 1,
    "hip":     2,
    "gable":   3,
    "mansard": 4,
}

_FOUNDATION_TYPE_MAP: dict[str, int] = {
    "strip":   0,
    "pad":     1,
    "raft":    2,
    "pile":    3,
    "caisson": 4,
}


class Preprocessor:
    """
    Prepares a single-row feature DataFrame from the raw JSON payloads.

    All encoding is deterministic and stateless — no fitted transformers
    are stored here.  The FeatureEngineer stage handles derived / combined
    features.
    """

    def prepare(self, building_schema: dict, cost_report: dict) -> pd.DataFrame:
        """
        Extract and encode features from the two source payloads.

        Args:
            building_schema: JSON payload from Component 01 (Architecture).
            cost_report:     JSON payload from Component 02 (Cost Estimation).

        Returns:
            pd.DataFrame: Single-row DataFrame with all raw encoded features.

        Raises:
            ValueError: If a required field is missing or has an invalid value.
        """
        try:
            # ── Building Schema fields ────────────────────────────────────────
            floors         = int(building_schema.get("floors", 1))
            footprint_sqm  = float(building_schema.get("footprint_sqm", 0.0))
            total_area_sqm = float(building_schema.get("total_area_sqm", 0.0))

            finish_grade_raw   = str(building_schema.get("finish_grade",   "standard")).lower().strip()
            roof_type_raw      = str(building_schema.get("roof_type",      "flat")).lower().strip()
            foundation_type_raw= str(building_schema.get("foundation_type","strip")).lower().strip()
            has_basement       = 1 if building_schema.get("has_basement", False) else 0
            is_coastal         = 1 if building_schema.get("location_coastal", False) else 0

            # district — free-text field, encoded by hash-mod for now
            # TODO: replace with a proper label encoder fitted on training data
            district_raw     = str(building_schema.get("district", "unknown")).lower().strip()
            district_encoded = abs(hash(district_raw)) % 25  # 25 districts in Sri Lanka

            # ── Categorical encoding ──────────────────────────────────────────
            finish_grade_encoded = _FINISH_GRADE_MAP.get(finish_grade_raw, 1)
            roof_type_encoded    = _ROOF_TYPE_MAP.get(roof_type_raw, 0)
            foundation_type_encoded = _FOUNDATION_TYPE_MAP.get(foundation_type_raw, 0)

            # ── Cost Report fields ────────────────────────────────────────────
            total_labour_days           = float(cost_report.get("total_labour_days", 0))
            structural_complexity_score = float(cost_report.get("structural_complexity_score", 1.0))

            # trade_value_breakdown — extract individual trade totals where available
            tvb            = cost_report.get("trade_value_breakdown", {})
            civil_value    = float(tvb.get("civil",    0.0))
            mep_value      = float(tvb.get("mep",      0.0))
            finishing_value= float(tvb.get("finishing",0.0))
            total_cost     = float(cost_report.get("total_cost", 0.0))

            # ── Assemble DataFrame ────────────────────────────────────────────
            data = {
                # Scale
                "floors":          floors,
                "footprint_sqm":   footprint_sqm,
                "total_area_sqm":  total_area_sqm,
                # Categorical (encoded)
                "finish_grade_encoded":    finish_grade_encoded,
                "roof_type_encoded":       roof_type_encoded,
                "foundation_type_encoded": foundation_type_encoded,
                "has_basement":            has_basement,
                # Location
                "is_coastal":       is_coastal,
                "district_encoded": district_encoded,
                # Labour
                "total_labour_days":           total_labour_days,
                "structural_complexity_score": structural_complexity_score,
                # Financial
                "civil_value":     civil_value,
                "mep_value":       mep_value,
                "finishing_value": finishing_value,
                "total_cost":      total_cost,
            }

            return pd.DataFrame([data])

        except (TypeError, AttributeError) as exc:
            raise ValueError(f"Preprocessor.prepare failed — invalid payload structure: {exc}") from exc
