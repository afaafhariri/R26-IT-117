"""Feature engineering for the ML cost prediction models.

Transforms raw BOQ + site metadata into a flat numeric feature matrix
that XGBoost can consume.
"""

import logging
from typing import Union

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

_TERRAIN_MAP = {"flat": 0, "sloped": 1, "hilly": 2, "rocky": 3}
_ROAD_ACCESS_MAP = {"paved": 0, "gravel": 1, "track": 2, "none": 3}
_ROOF_TYPE_MAP = {"flat": 0, "gable": 1, "hip": 2, "mansard": 3}
_FINISH_GRADE_MAP = {"economy": 0, "mid": 1, "luxury": 2}


class FeatureEngineer:
    """Builds a numeric feature DataFrame from BOQ + site data."""

    def build_features(
        self,
        boq: dict,
        site_schema: dict,
        finish_grade: str,
    ) -> pd.DataFrame:
        """Construct the ML feature matrix from Layer 1 and site inputs.

        Args:
            boq: Consolidated BOQ dict returned by BOQEngine.run().
            site_schema: Site/building metadata (coastal flag, terrain, road access, etc.).
            finish_grade: 'economy', 'mid', or 'luxury'.

        Returns:
            Single-row pd.DataFrame of numeric features ready for model inference.
        """
        structural = boq.get("structural", {})
        finishing = boq.get("finishing", {})
        services = boq.get("services", {})
        summary = boq.get("summary", {})

        # ---- BOQ features ------------------------------------------------
        concrete_m3 = float(summary.get("total_concrete_m3", 0.0))
        steel_kg = float(summary.get("steel_kg_estimate", 0.0))
        brickwork_m3 = float(summary.get("total_brickwork_m3", 0.0))
        floor_area_sqm = float(summary.get("floor_area_sqm", 1.0))
        wall_plaster_sqm = float(finishing.get("wall_plaster_sqm", 0.0))
        door_count = float(finishing.get("door_count", 0))
        window_count = float(finishing.get("window_count", 0))
        bathroom_count = float(site_schema.get("bathroom_count", 1))

        # ---- Ratio features ----------------------------------------------
        concrete_per_sqm = concrete_m3 / max(floor_area_sqm, 1.0)
        steel_to_concrete_ratio = steel_kg / max(concrete_m3, 0.001)
        opening_count = door_count + window_count
        perimeter = float(site_schema.get("perimeter", 0.0))
        wall_area = float(
            structural.get("external_brickwork_m3", 0.0) / 0.23
        )  # recover wall area from volume
        opening_to_wall_ratio = opening_count / max(wall_area, 1.0)
        perimeter_to_area_ratio = perimeter / max(floor_area_sqm, 1.0)

        # ---- Location features -------------------------------------------
        is_coastal = int(bool(site_schema.get("is_coastal", False)))
        terrain_raw = str(site_schema.get("terrain", "flat")).lower()
        terrain_encoded = _TERRAIN_MAP.get(terrain_raw, 0)
        road_access_raw = str(site_schema.get("road_access", "paved")).lower()
        road_access_encoded = _ROAD_ACCESS_MAP.get(road_access_raw, 0)

        # ---- Spec features -----------------------------------------------
        finish_grade_encoded = _FINISH_GRADE_MAP.get(finish_grade.lower(), 1)
        roof_type_raw = str(site_schema.get("roof_type", "gable")).lower()
        roof_type_encoded = _ROOF_TYPE_MAP.get(roof_type_raw, 1)
        floors = int(site_schema.get("floors", 1))

        features = {
            # BOQ
            "concrete_m3": concrete_m3,
            "steel_kg": steel_kg,
            "brickwork_m3": brickwork_m3,
            "floor_area_sqm": floor_area_sqm,
            "wall_plaster_sqm": wall_plaster_sqm,
            "door_count": door_count,
            "window_count": window_count,
            "bathroom_count": bathroom_count,
            # Ratios
            "concrete_per_sqm": concrete_per_sqm,
            "steel_to_concrete_ratio": steel_to_concrete_ratio,
            "opening_to_wall_ratio": opening_to_wall_ratio,
            "perimeter_to_area_ratio": perimeter_to_area_ratio,
            # Location
            "is_coastal": is_coastal,
            "terrain_encoded": terrain_encoded,
            "road_access_encoded": road_access_encoded,
            # Spec
            "finish_grade_encoded": finish_grade_encoded,
            "roof_type_encoded": roof_type_encoded,
            "floors": floors,
        }

        df = pd.DataFrame([features])
        df = df.replace([np.inf, -np.inf], 0.0).fillna(0.0)
        logger.debug("Feature matrix shape: %s", df.shape)
        return df

    @staticmethod
    def feature_names() -> list[str]:
        """Return the ordered list of feature column names."""
        return [
            "concrete_m3", "steel_kg", "brickwork_m3", "floor_area_sqm",
            "wall_plaster_sqm", "door_count", "window_count", "bathroom_count",
            "concrete_per_sqm", "steel_to_concrete_ratio", "opening_to_wall_ratio",
            "perimeter_to_area_ratio", "is_coastal",
            "terrain_encoded", "road_access_encoded", "finish_grade_encoded",
            "roof_type_encoded", "floors",
        ]
