"""Structural Bill of Quantities calculator for concrete, masonry, and RC elements."""

import logging

logger = logging.getLogger(__name__)


class StructuralBOQ:
    """Computes structural quantities from a Building Schema."""

    def calculate(self, building_schema: dict) -> dict:
        """Return structural BOQ quantities derived from building geometry.

        Args:
            building_schema: Validated Building Schema dict from Component 01.

        Returns:
            Dict of quantity keys mapped to float values with units in the key name.
        """
        perimeter: float = float(building_schema.get("perimeter", 0.0))
        footprint_sqm: float = float(building_schema.get("footprint_sqm", 0.0))
        floors: int = int(building_schema.get("floors", 1))
        floor_height: float = float(building_schema.get("floor_height", 3.0))
        column_count: int = int(building_schema.get("column_count", 0))
        wall_height: float = float(building_schema.get("wall_height", floor_height))
        openings_sqm: float = float(building_schema.get("openings_sqm", 0.0))
        internal_wall_length: float = float(
            building_schema.get("internal_wall_length", footprint_sqm / floor_height)
        )

        # Derive column count from perimeter if not explicitly provided
        if column_count == 0:
            column_count = max(4, int(perimeter / 4))

        excavation_depth: float = float(building_schema.get("excavation_depth", 1.5))

        foundation_excavation_m3 = perimeter * excavation_depth * 0.6
        blinding_concrete_m3 = perimeter * 0.6 * 0.05
        foundation_concrete_m3 = perimeter * 0.6 * 0.45
        rc_columns_m3 = column_count * 0.23 * 0.23 * floor_height * floors
        rc_slab_m3 = footprint_sqm * 0.125 * floors
        external_wall_area = (perimeter * wall_height * floors) - openings_sqm
        external_brickwork_m3 = max(0.0, external_wall_area * 0.23)
        internal_blockwork_m3 = internal_wall_length * wall_height * 0.115 * floors
        roof_area_sqm = footprint_sqm * 1.30

        result = {
            "foundation_excavation_m3": round(foundation_excavation_m3, 3),
            "blinding_concrete_m3": round(blinding_concrete_m3, 3),
            "foundation_concrete_m3": round(foundation_concrete_m3, 3),
            "rc_columns_m3": round(rc_columns_m3, 3),
            "rc_slab_m3": round(rc_slab_m3, 3),
            "external_brickwork_m3": round(external_brickwork_m3, 3),
            "internal_blockwork_m3": round(internal_blockwork_m3, 3),
            "roof_area_sqm": round(roof_area_sqm, 3),
        }
        logger.debug("Structural BOQ: %s", result)
        return result
