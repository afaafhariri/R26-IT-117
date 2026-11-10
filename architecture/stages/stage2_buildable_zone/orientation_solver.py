"""Determines optimal building orientation within the buildable zone."""

from utils.logger import get_logger

_logger = get_logger("orientation_solver")

_ROAD_TO_ENTRANCE: dict[str, str] = {
    "national_road": "south",
    "provincial":    "south",
    "local":         "south",
    "lane":          "east",
}

_ENTRANCE_TO_DEGREES: dict[str, float] = {
    "north": 0.0,
    "east":  90.0,
    "south": 180.0,
    "west":  270.0,
}


class OrientationSolver:
    """Determines optimal building placement within the buildable zone based on:

    1. Road access position (building entrance should face road).
    2. Solar orientation for Sri Lankan tropical climate (6°N latitude): south-facing
       habitable rooms receive morning light; north-facing verandahs provide shade.
    3. Visual and acoustic separation from adjacent boundaries.
    """

    def solve(self, buildable_polygon: list, site_schema: dict) -> dict:
        """Determines recommended building orientation and entrance placement.

        Args:
            buildable_polygon: Coordinate list from BuildableZoneCalculator.
            site_schema: Full Site Schema from Stage 1, including road_access,
                road_access_side, and orientation_degrees fields.

        Returns:
            dict: {
                recommended_orientation_degrees: float,
                entrance_side: str (north|south|east|west),
                optimal_placement: {x_offset_m: float, y_offset_m: float},
                solar_notes: str
            }
        """
        # road_access_side is read directly off the plan's boundary declarations
        # (e.g. "South by: Lane") — use it when available, since it reflects
        # this specific plot rather than a generic assumption about road type.
        # Falls back to the road-type table only when that extraction found
        # nothing (e.g. the plan's boundary text didn't mention a road at all).
        boundary_side = site_schema.get("road_access_side")
        if boundary_side in ("north", "east", "south", "west"):
            entrance_side: str = boundary_side
        else:
            road_type: str = site_schema.get("road_access", "local")
            entrance_side = _ROAD_TO_ENTRANCE.get(road_type, "south")

        plot_orientation: float = site_schema.get("orientation_degrees", 0.0)
        recommended_degrees = (
            _ENTRANCE_TO_DEGREES.get(entrance_side, 180.0) + plot_orientation
        ) % 360

        # Sri Lanka at ~6°N: south-facing rooms receive morning/afternoon sunlight
        solar_notes = (
            "Sri Lanka (6°N latitude): orient living and bedroom windows to the south "
            "for morning light. Use north-facing verandahs and roof overhangs of ≥0.9 m "
            "to minimise direct solar heat gain. Prevailing SW monsoon wind is from the "
            "southwest — place openings on SW and NE walls for cross-ventilation."
        )

        # Centroid-relative offset placeholder
        # TODO Sprint 6: integrate solar path simulation per district latitude
        optimal_placement = {"x_offset_m": 0.0, "y_offset_m": 0.0}

        result = {
            "recommended_orientation_degrees": round(recommended_degrees, 2),
            "entrance_side": entrance_side,
            "optimal_placement": optimal_placement,
            "solar_notes": solar_notes,
        }

        _logger.info(
            "Orientation solved: entrance=%s, orientation=%.1f°",
            entrance_side,
            recommended_degrees,
        )
        return result
