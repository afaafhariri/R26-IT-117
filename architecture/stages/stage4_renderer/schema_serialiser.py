"""
schema_serialiser.py — Produces the Building Schema JSON that feeds Component 02.

Combines the approved floor plan with site and buildable zone data into
the canonical Building Schema used by downstream components.
"""

import uuid
import logging
from typing import Any

import jsonschema

logger = logging.getLogger(__name__)

# ── Building Schema JSON Schema ───────────────────────────────────────────

BUILDING_SCHEMA = {
    "type": "object",
    "required": ["plan_id", "site", "building", "rooms", "materials_schedule", "finish_grade"],
    "properties": {
        "plan_id": {"type": "string"},
        "site": {"type": "object"},
        "building": {
            "type": "object",
            "required": ["floors", "footprint_sqm", "total_area_sqm", "roof_type", "foundation_type"],
            "properties": {
                "floors":          {"type": "integer", "minimum": 1},
                "footprint_sqm":   {"type": "number",  "minimum": 0},
                "total_area_sqm":  {"type": "number",  "minimum": 0},
                "roof_type":       {"type": "string"},
                "foundation_type": {"type": "string"},
            },
        },
        "rooms": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name", "floor", "area_sqm"],
            },
        },
        "materials_schedule": {"type": "object"},
        "finish_grade": {"type": "string"},
    },
    "additionalProperties": True,
}

# Typical Sri Lankan material schedules keyed by finish grade
_MATERIALS: dict[str, dict[str, str]] = {
    "budget": {
        "walls":       "Sand-cement block, lime plaster",
        "floors":      "Ceramic tile 300×300",
        "roof":        "Asbestos-free corrugated fibre cement",
        "windows":     "Aluminium single-glazed sliding",
        "doors":       "Hollow-core flush door",
        "foundation":  "Strip foundation, plain concrete",
    },
    "standard": {
        "walls":       "Sand-cement block, cement-sand plaster",
        "floors":      "Ceramic tile 600×600",
        "roof":        "Clay/concrete roof tiles on timber trusses",
        "windows":     "Aluminium powder-coated casement",
        "doors":       "Solid-core flush door",
        "foundation":  "Reinforced strip foundation",
    },
    "premium": {
        "walls":       "Sand-cement block, skim-coat finish",
        "floors":      "Polished porcelain tile 600×600",
        "roof":        "Concrete tile on steel trusses",
        "windows":     "uPVC double-glazed casement",
        "doors":       "Solid timber panelled door",
        "foundation":  "Reinforced raft foundation",
    },
    "luxury": {
        "walls":       "RC frame with brick infill, Italian plaster",
        "floors":      "Italian marble / engineered timber",
        "roof":        "Concrete flat slab with waterproof membrane",
        "windows":     "Aluminium curtain wall double-glazed",
        "doors":       "Solid hardwood door with steel frame",
        "foundation":  "Bored pile foundation",
    },
}


class SchemaSerialiser:
    """Serialises all stage outputs into the canonical Building Schema."""

    def serialise(
        self,
        floor_plan: dict,
        site_schema: dict,
        buildable_zone: dict,
    ) -> dict:
        """
        Assemble the Building Schema JSON from stage outputs.

        Args:
            floor_plan:     Approved floor plan dict from Stage 3.
            site_schema:    Site Schema from Stage 1.
            buildable_zone: Buildable Zone dict from Stage 2.

        Returns:
            Validated Building Schema dict conforming to BUILDING_SCHEMA.

        Raises:
            ValueError: If the assembled schema fails jsonschema validation.
        """
        finish_grade = self._infer_finish_grade(floor_plan)
        footprint = buildable_zone.get("buildable_area_sqm", 0.0)
        floors = floor_plan.get("total_floors", buildable_zone.get("recommended_floors", 1))
        total_area = round(footprint * floors, 2)

        schema: dict[str, Any] = {
            "plan_id": site_schema.get("plan_id") or str(uuid.uuid4()),
            "site": site_schema.get("site", {}),
            "building": {
                "floors":          int(floors),
                "footprint_sqm":   round(footprint, 2),
                "total_area_sqm":  total_area,
                "roof_type":       floor_plan.get("roof_type", "gable"),
                "foundation_type": floor_plan.get("foundation_type", "strip"),
            },
            "rooms": self._serialise_rooms(floor_plan.get("rooms", [])),
            "materials_schedule": _MATERIALS.get(finish_grade, _MATERIALS["standard"]),
            "finish_grade": finish_grade,
            # Carry forward boundary and zone data for Component 02
            "boundaries":      site_schema.get("boundaries", {}),
            "buildable_zone":  {
                "polygon":      buildable_zone.get("buildable_polygon", []),
                "area_sqm":     buildable_zone.get("buildable_area_sqm", 0.0),
                "setbacks":     buildable_zone.get("setbacks_applied", {}),
                "orientation":  buildable_zone.get("optimal_orientation", {}),
            },
        }

        self._validate(schema)
        return schema

    # ── Private helpers ───────────────────────────────────────────────────

    def _validate(self, schema: dict) -> None:
        try:
            jsonschema.validate(instance=schema, schema=BUILDING_SCHEMA)
        except jsonschema.ValidationError as exc:
            raise ValueError(f"Building Schema validation failed: {exc.message}") from exc

    @staticmethod
    def _serialise_rooms(rooms: list[dict]) -> list[dict]:
        """
        Normalise the room list for the Building Schema.
        Adds default fields if missing.
        """
        serialised = []
        for room in rooms:
            serialised.append(
                {
                    "name":        room.get("name", "Unknown"),
                    "floor":       room.get("floor", 1),
                    "area_sqm":    round(room.get("area_sqm", 0.0), 2),
                    "polygon":     room.get("polygon", []),
                    "has_window":  room.get("has_window", False),
                    "has_door":    room.get("has_door", True),
                    "adjacencies": room.get("adjacencies", []),
                }
            )
        return serialised

    @staticmethod
    def _infer_finish_grade(floor_plan: dict) -> str:
        """
        Extract finish_grade from the floor plan if present, else default to 'standard'.
        The LLM prompt asks for this field; if absent, fall back gracefully.
        """
        grade = floor_plan.get("finish_grade", "standard").lower().strip()
        return grade if grade in _MATERIALS else "standard"
