"""
FeatureEngineer — Component 04 Pipeline Step 2.

Derives analytical features from the preprocessed DataFrame.
All computations are vectorised over rows so that batch inference
(multiple projects at once) works without modification.
"""

import math
import numpy as np
import pandas as pd


class FeatureEngineer:
    """
    Builds derived features grouped into five categories:

    - Scale:      size-based features (area, floors, perimeter)
    - Complexity: structural and finish complexity signals
    - Labour:     labour-density ratios
    - Financial:  cost-density and material/labour split
    - Location:   coastal flag and district encoding
    """

    # Columns that must arrive from the Preprocessor stage
    _REQUIRED_COLUMNS: list[str] = [
        "floors", "footprint_sqm", "total_area_sqm",
        "finish_grade_encoded", "roof_type_encoded", "foundation_type_encoded",
        "has_basement", "is_coastal", "district_encoded",
        "total_labour_days", "structural_complexity_score",
        "civil_value", "mep_value", "finishing_value", "total_cost",
    ]

    def build_features(self, preprocessed_df: pd.DataFrame) -> pd.DataFrame:
        """
        Derive all model features from the preprocessed DataFrame.

        Args:
            preprocessed_df: Output of Preprocessor.prepare() — one row per project.

        Returns:
            pd.DataFrame: Augmented DataFrame with all feature columns appended.

        Raises:
            ValueError: If a required input column is missing.
        """
        self._validate_columns(preprocessed_df)

        df = preprocessed_df.copy()

        # ── Scale features ────────────────────────────────────────────────────
        df["perimeter_m"] = df["footprint_sqm"].apply(
            lambda x: 4.0 * math.sqrt(x) if x > 0 else 0.0
        )
        df["area_per_floor"] = np.where(
            df["floors"] > 0,
            df["total_area_sqm"] / df["floors"],
            df["total_area_sqm"],
        )

        # ── Complexity features ───────────────────────────────────────────────
        # roof_complexity: flat=0 is simple; anything else is complex
        df["roof_complexity"] = (df["roof_type_encoded"] > 0).astype(int)

        # ── Labour features ───────────────────────────────────────────────────
        df["labour_days_per_sqm"] = np.where(
            df["total_area_sqm"] > 0,
            df["total_labour_days"] / df["total_area_sqm"],
            0.0,
        )

        # ── Financial features ────────────────────────────────────────────────
        df["cost_per_sqm"] = np.where(
            df["total_area_sqm"] > 0,
            df["total_cost"] / df["total_area_sqm"],
            0.0,
        )

        labour_cost  = df["civil_value"]   # civil trade cost used as labour proxy
        material_cost = df["mep_value"] + df["finishing_value"]
        df["material_to_labour_ratio"] = np.where(
            labour_cost > 0,
            material_cost / labour_cost,
            1.0,
        )

        # ── Location features ─────────────────────────────────────────────────
        # is_coastal and district_encoded already present; no further derivation needed.

        # TODO: add interaction terms (e.g. is_coastal * floors) once training
        #       data confirms their predictive value.

        return df

    # ── Private helpers ───────────────────────────────────────────────────────

    def _validate_columns(self, df: pd.DataFrame) -> None:
        missing = [c for c in self._REQUIRED_COLUMNS if c not in df.columns]
        if missing:
            raise ValueError(
                f"FeatureEngineer received a DataFrame missing columns: {missing}"
            )
