"""Shapely-based buildable zone calculator applying NBC setback buffers.

Boundary polygons from Stage 1 are normalised to [0, 1] relative to the
scan image dimensions. This module uses the real-world area_sqm from the
site schema to derive a scale factor so that setback distances (in metres)
are applied correctly and all output areas are in real square metres.
"""

import math

from shapely.geometry import Polygon, mapping
from shapely.validation import make_valid

from utils.logger import get_logger

_logger = get_logger("polygon_calculator")


class BuildableZoneCalculator:
    """Computes the maximum legal construction footprint by applying inward
    setback buffers and Building Coverage Ratio constraints.
    """

    def __init__(self) -> None:
        _logger.info("BuildableZoneCalculator initialised")

    def _validate_polygon(self, polygon: list, real_area_sqm: float) -> Polygon:
        """Validates polygon and checks real-world area is above 50 sqm minimum.

        Args:
            polygon: List of [x, y] normalised coordinate pairs (0–1).
            real_area_sqm: Real-world plot area in square metres from NER.

        Returns:
            Polygon: Valid Shapely Polygon in normalised coordinate space.

        Raises:
            ValueError: If polygon has fewer than 3 points, is self-intersecting,
                or the real area is below the 50 sqm minimum.
        """
        if len(polygon) < 3:
            raise ValueError(
                f"Polygon must have at least 3 vertices, got {len(polygon)}"
            )

        shapely_poly = Polygon(polygon)

        if not shapely_poly.is_simple:
            raise ValueError(
                "Polygon is self-intersecting. Supply a simple (non-self-crossing) boundary."
            )

        if not shapely_poly.is_valid:
            shapely_poly = make_valid(shapely_poly)

        # Validate against real-world area, not normalised polygon area
        if real_area_sqm < 50:
            raise ValueError(
                f"Plot area {real_area_sqm:.1f} sqm is below the 50 sqm minimum"
            )

        return shapely_poly

    def calculate(
        self,
        boundary_polygon: list,
        setbacks: dict,
        coverage_ratio: float,
        floors_requested: int,
        real_area_sqm: float = 0.0,
    ) -> dict:
        """Computes the maximum legal construction footprint.

        Converts setback distances from metres to normalised units using the
        real-world area, applies Shapely inward buffering, then converts all
        output areas back to real square metres.

        Args:
            boundary_polygon: Normalised [0,1] coordinate list from Stage 1.
            setbacks: {front, rear, side} distances in metres.
            coverage_ratio: BCR from NBCConstraintEngine (0.0–1.0).
            floors_requested: Number of floors requested by the user.
            real_area_sqm: Real plot area in sqm from site schema (used for
                scale calibration and area output).

        Returns:
            dict with buildable_polygon (normalised), max_footprint_sqm,
            max_total_built_sqm, recommended_floors, setback_margins,
            coverage_achieved.
        """
        site_polygon = self._validate_polygon(boundary_polygon, real_area_sqm)

        norm_area = site_polygon.area  # area in normalised [0,1]² space

        # Scale factor: 1 normalised unit = scale_factor metres
        # derived from sqrt(real_area / norm_area)
        if real_area_sqm > 0 and norm_area > 0:
            scale_factor = math.sqrt(real_area_sqm / norm_area)
        else:
            scale_factor = 1.0

        _logger.info(
            "Site polygon: norm_area=%.4f, real_area=%.1f sqm, scale=%.2f m/unit, "
            "setbacks front=%.1f rear=%.1f side=%.1f",
            norm_area, real_area_sqm, scale_factor,
            setbacks["front"], setbacks["rear"], setbacks["side"],
        )

        # Convert setback metres → normalised units for Shapely buffering
        min_setback_m = min(setbacks["front"], setbacks["rear"], setbacks["side"])
        min_setback_norm = min_setback_m / scale_factor

        # TODO Sprint 5: apply directional buffers based on plot orientation
        buildable = site_polygon.buffer(-min_setback_norm, join_style=2)

        if buildable.is_empty or buildable.area <= 0:
            _logger.warning(
                "Setback buffer produced empty polygon — halving setback distance"
            )
            buildable = site_polygon.buffer(-min_setback_norm * 0.5, join_style=2)

        # Convert buildable area back to real sqm
        buildable_sqm  = buildable.area * (scale_factor ** 2)
        bcr_max_sqm    = real_area_sqm * coverage_ratio
        actual_footprint = min(buildable_sqm, bcr_max_sqm)

        recommended_floors = 1
        if real_area_sqm >= 200:
            recommended_floors = 2
        if real_area_sqm > 500:
            recommended_floors = 3

        max_total_built  = actual_footprint * floors_requested
        coverage_achieved = round(actual_footprint / real_area_sqm, 4) if real_area_sqm > 0 else 0.0

        try:
            buildable_coords = list(mapping(buildable)["coordinates"][0])
        except (KeyError, IndexError):
            buildable_coords = list(mapping(buildable.convex_hull)["coordinates"][0])

        result = {
            "buildable_polygon": [[c[0], c[1]] for c in buildable_coords],
            "max_footprint_sqm": round(actual_footprint, 2),
            "max_total_built_sqm": round(max_total_built, 2),
            "recommended_floors": recommended_floors,
            "setback_margins": setbacks,
            "coverage_achieved": coverage_achieved,
        }

        _logger.info(
            "Buildable zone calculated: footprint=%.2f sqm, coverage=%.2f",
            actual_footprint, coverage_achieved,
        )
        return result
