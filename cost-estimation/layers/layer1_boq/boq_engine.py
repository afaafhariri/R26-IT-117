"""BOQ Engine — orchestrates all three BOQ sub-calculators and merges their output."""

import logging

from .structural_boq import StructuralBOQ
from .finishing_boq import FinishingBOQ
from .services_boq import ServicesBOQ

logger = logging.getLogger(__name__)


class BOQEngine:
    """Unified entry-point for Layer 1: produces a consolidated BOQ from a Building Schema."""

    def __init__(self) -> None:
        self._structural = StructuralBOQ()
        self._finishing = FinishingBOQ()
        self._services = ServicesBOQ()

    def run(self, building_schema: dict) -> dict:
        """Execute all three BOQ calculators and return a merged BOQ dict.

        Args:
            building_schema: Validated Building Schema dict from Component 01.
                             Must include at minimum: footprint_sqm, perimeter, floors,
                             finish_grade, rooms (dict), bathroom_count.

        Returns:
            Consolidated BOQ dict with keys: 'structural', 'finishing', 'services',
            and a flat 'summary' with key aggregates used by downstream layers.
        """
        finish_grade: str = building_schema.get("finish_grade", "mid")
        rooms: dict = building_schema.get("rooms", {})

        logger.info("Running BOQ Engine for district=%s floors=%s grade=%s",
                    building_schema.get("district", "unknown"),
                    building_schema.get("floors", 1),
                    finish_grade)

        structural = self._structural.calculate(building_schema)
        finishing = self._finishing.calculate(building_schema, finish_grade)
        services = self._services.calculate(rooms)

        # Aggregate steel estimate: ~110 kg/m3 concrete (indicative)
        total_concrete_m3 = (
            structural["foundation_concrete_m3"]
            + structural["blinding_concrete_m3"]
            + structural["rc_columns_m3"]
            + structural["rc_slab_m3"]
        )
        steel_kg_estimate = round(total_concrete_m3 * 110.0, 1)

        summary = {
            "total_concrete_m3": round(total_concrete_m3, 3),
            "steel_kg_estimate": steel_kg_estimate,
            "total_brickwork_m3": round(
                structural["external_brickwork_m3"] + structural["internal_blockwork_m3"], 3
            ),
            "floor_area_sqm": building_schema.get("footprint_sqm", 0.0)
            * building_schema.get("floors", 1),
            "finish_grade": finish_grade,
            "electrical_points": services["electrical_points"],
            "total_plumbing_fixtures": services["total_plumbing_fixtures"],
        }

        return {
            "structural": structural,
            "finishing": finishing,
            "services": services,
            "summary": summary,
        }
