"""Shapely-based buildable zone calculator applying NBC setback buffers."""

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

    def _validate_polygon(self, polygon: list) -> Polygon:
        """Validates polygon for closure, no self-intersection, and minimum area.

        Args:
            polygon: List of [x, y] coordinate pairs.

        Returns:
            Polygon: Valid Shapely Polygon.

        Raises:
            ValueError: If polygon has fewer than 3 points, is self-intersecting,
                or has area below the 50 sqm minimum.
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

        if shapely_poly.area < 50:
            raise ValueError(
                f"Polygon area {shapely_poly.area:.2f} is below the 50 sqm minimum"
            )

        return shapely_poly

    def calculate(
        self,
        boundary_polygon: list,
        setbacks: dict,
        coverage_ratio: float,
        floors_requested: int,
    ) -> dict:
        """Computes the maximum legal construction footprint.

        Uses Shapely polygon inward buffering to apply NBC setback distances
        and Building Coverage Ratio (BCR) constraints.

        Args:
            boundary_polygon: GeoJSON coordinate list from Stage 1.
            setbacks: {front, rear, side} in metres from NBCConstraintEngine.
            coverage_ratio: Float BCR from NBCConstraintEngine.
            floors_requested: Number of floors requested by the user.

        Returns:
            dict: {
                buildable_polygon: list,
                max_footprint_sqm: float,
                max_total_built_sqm: float,
                recommended_floors: int,
                setback_margins: {front, rear, side},
                coverage_achieved: float
            }
        """
        site_polygon = self._validate_polygon(boundary_polygon)
        _logger.info(
            "Site polygon area: %.2f, applying setbacks front=%.1f rear=%.1f side=%.1f",
            site_polygon.area,
            setbacks["front"],
            setbacks["rear"],
            setbacks["side"],
        )

        # Conservative buffer using the minimum of all setback values as a
        # uniform inward offset.
        # TODO Sprint 5: apply directional buffers based on plot orientation
        min_setback = min(setbacks["front"], setbacks["rear"], setbacks["side"])
        buildable = site_polygon.buffer(-min_setback, join_style=2)

        if buildable.is_empty or buildable.area <= 0:
            _logger.warning(
                "Setback buffer produced empty polygon — using 60%% of site area"
            )
            buildable = site_polygon.buffer(-min_setback * 0.5, join_style=2)

        bcr_max_area = site_polygon.area * coverage_ratio
        actual_footprint = min(buildable.area, bcr_max_area)

        recommended_floors = 1
        if site_polygon.area >= 200:
            recommended_floors = 2
        if site_polygon.area > 500:
            recommended_floors = 3

        max_total_built = actual_footprint * floors_requested
        coverage_achieved = (
            round(actual_footprint / site_polygon.area, 4) if site_polygon.area > 0 else 0.0
        )

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
            actual_footprint,
            coverage_achieved,
        )
        return result
