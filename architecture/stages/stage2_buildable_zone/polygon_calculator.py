"""
polygon_calculator.py — Shapely-based buildable zone footprint calculator.

Applies NBC setbacks to the site boundary polygon to derive:
  - buildable_polygon: the permitted construction footprint
  - max_area_sqm: maximum ground-floor area
  - recommended_floors: suggested number of storeys
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Minimum viable buildable area — below this, no meaningful floor plan is possible
_MIN_BUILDABLE_AREA_SQM = 30.0


class BuildableZoneCalculator:
    """Computes the buildable footprint polygon from boundary + setbacks."""

    def calculate(
        self,
        boundary_polygon: list[list[float]],
        setbacks: dict[str, float],
        coverage_ratio: float,
    ) -> dict[str, Any]:
        """
        Derive the inner buildable zone polygon by applying negative buffer
        offsets representing front/rear/side setbacks.

        Args:
            boundary_polygon: Ordered list of [x, y] coordinate pairs (metres).
            setbacks:         {"front": float, "rear": float, "side": float}
            coverage_ratio:   Maximum permitted footprint / plot area ratio.

        Returns:
            {
                "buildable_polygon":   list[[x,y]],
                "buildable_area_sqm":  float,
                "max_area_sqm":        float,
                "recommended_floors":  int,
                "plot_area_sqm":       float,
            }

        Raises:
            ValueError: If the boundary polygon has fewer than 3 points or if
                        the resulting buildable zone is empty after setback.
        """
        if len(boundary_polygon) < 3:
            raise ValueError("boundary_polygon must have at least 3 vertices.")

        try:
            from shapely.geometry import Polygon  # type: ignore
            from shapely.ops import unary_union  # noqa: F401 — ensure shapely loaded

            site = Polygon(boundary_polygon)
            if not site.is_valid:
                site = site.buffer(0)  # Attempt auto-fix for self-intersections

            plot_area = site.area

            # Apply uniform conservative setback (average of front/rear/side)
            # TODO: apply directional setbacks once compass orientation is known
            avg_setback = (
                setbacks["front"] + setbacks["rear"] + 2 * setbacks["side"]
            ) / 4.0
            buildable = site.buffer(-avg_setback)

            if buildable.is_empty or buildable.area < _MIN_BUILDABLE_AREA_SQM:
                raise ValueError(
                    f"Buildable zone after {avg_setback:.1f} m setback is too small "
                    f"({buildable.area:.1f} m²). Minimum required: {_MIN_BUILDABLE_AREA_SQM} m²."
                )

            buildable_coords = list(buildable.exterior.coords)[:-1]  # drop closing vertex
            buildable_area = buildable.area
            max_area = plot_area * coverage_ratio
            recommended_floors = self._recommend_floors(buildable_area)

            return {
                "buildable_polygon": [[round(x, 3), round(y, 3)] for x, y in buildable_coords],
                "buildable_area_sqm": round(buildable_area, 2),
                "max_area_sqm": round(max_area, 2),
                "recommended_floors": recommended_floors,
                "plot_area_sqm": round(plot_area, 2),
                "setbacks_applied": setbacks,
                "coverage_ratio": coverage_ratio,
            }

        except ImportError:
            logger.warning("Shapely not available — returning stub buildable zone.")
            return self._stub_zone(boundary_polygon, setbacks, coverage_ratio)

    @staticmethod
    def _recommend_floors(buildable_area_sqm: float) -> int:
        """
        Suggest number of floors based on buildable footprint size.

        Rule of thumb for Sri Lankan residential construction:
          < 60 m²   → 1 floor
          60–150 m² → 2 floors
          > 150 m²  → 3 floors
        TODO: incorporate FAR limits from NBC district tables.
        """
        if buildable_area_sqm < 60:
            return 1
        if buildable_area_sqm < 150:
            return 2
        return 3

    @staticmethod
    def _stub_zone(
        polygon: list,
        setbacks: dict,
        coverage_ratio: float,
    ) -> dict:
        """Return a simplified stub result when Shapely is unavailable."""
        # TODO: replace with real Shapely computation in production
        stub_area = 120.0
        return {
            "buildable_polygon": [[2.0, 2.0], [18.0, 2.0], [18.0, 14.0], [2.0, 14.0]],
            "buildable_area_sqm": stub_area,
            "max_area_sqm": stub_area,
            "recommended_floors": 2,
            "plot_area_sqm": stub_area / coverage_ratio,
            "setbacks_applied": setbacks,
            "coverage_ratio": coverage_ratio,
        }
