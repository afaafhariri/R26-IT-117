"""Finishing Bill of Quantities — tiles, plaster, ceilings, joinery, and paint."""

import logging
from typing import Literal

logger = logging.getLogger(__name__)

FinishGrade = Literal["economy", "mid", "luxury"]

# Multipliers applied to base quantities by finish grade
_GRADE_FACTORS: dict[str, dict[str, float]] = {
    "economy": {
        "floor_tile_sqm": 0.85,
        "wall_plaster_sqm": 1.00,
        "ceiling_sqm": 0.80,
        "door_count": 0.90,
        "window_count": 0.85,
        "paint_sqm": 1.00,
    },
    "mid": {
        "floor_tile_sqm": 1.00,
        "wall_plaster_sqm": 1.00,
        "ceiling_sqm": 1.00,
        "door_count": 1.00,
        "window_count": 1.00,
        "paint_sqm": 1.00,
    },
    "luxury": {
        "floor_tile_sqm": 1.10,
        "wall_plaster_sqm": 1.05,
        "ceiling_sqm": 1.20,
        "door_count": 1.15,
        "window_count": 1.20,
        "paint_sqm": 1.05,
    },
}


class FinishingBOQ:
    """Computes finishing quantities adjusted for finish grade."""

    def calculate(self, building_schema: dict, finish_grade: str) -> dict:
        """Return finishing BOQ quantities for the given grade.

        Args:
            building_schema: Building Schema dict from Component 01.
            finish_grade: One of 'economy', 'mid', 'luxury'.

        Returns:
            Dict of finishing quantity keys with float values.
        """
        grade = finish_grade.lower()
        if grade not in _GRADE_FACTORS:
            logger.warning("Unknown finish_grade '%s', defaulting to 'mid'.", finish_grade)
            grade = "mid"

        factors = _GRADE_FACTORS[grade]
        footprint_sqm: float = float(building_schema.get("footprint_sqm", 0.0))
        floors: int = int(building_schema.get("floors", 1))
        perimeter: float = float(building_schema.get("perimeter", 0.0))
        wall_height: float = float(building_schema.get("wall_height", 3.0))
        room_count: int = int(building_schema.get("room_count", 4))
        bathroom_count: int = int(building_schema.get("bathroom_count", 2))

        total_floor_area = footprint_sqm * floors
        total_wall_area = perimeter * wall_height * floors

        # Base quantities (mid-grade baseline)
        base_floor_tile_sqm = total_floor_area * 0.90
        base_wall_plaster_sqm = total_wall_area * 2.0
        base_ceiling_sqm = total_floor_area
        base_door_count = room_count + bathroom_count + 1  # +1 for main entrance
        base_window_count = room_count * 2
        base_paint_sqm = total_wall_area + total_floor_area

        result = {
            "floor_tile_sqm": round(base_floor_tile_sqm * factors["floor_tile_sqm"], 2),
            "wall_plaster_sqm": round(base_wall_plaster_sqm * factors["wall_plaster_sqm"], 2),
            "ceiling_sqm": round(base_ceiling_sqm * factors["ceiling_sqm"], 2),
            "door_count": max(1, round(base_door_count * factors["door_count"])),
            "window_count": max(2, round(base_window_count * factors["window_count"])),
            "paint_sqm": round(base_paint_sqm * factors["paint_sqm"], 2),
            "finish_grade": grade,
        }
        logger.debug("Finishing BOQ (%s): %s", grade, result)
        return result
