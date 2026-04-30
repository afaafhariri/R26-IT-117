"""Assembles and validates the Building Schema JSON for Component 02 handoff."""

import json
import os
from pathlib import Path

import jsonschema

from utils.logger import get_logger

_logger = get_logger("schema_serialiser")

_BUDGET_TO_FINISH: dict[str, str] = {
    "economy": "economy",
    "medium":  "medium",
    "luxury":  "luxury",
}
_STYLE_TO_ROOF: dict[str, str] = {
    "modern":        "flat",
    "traditional":   "hip",
    "contemporary":  "gable",
}


class SchemaSerialiser:
    """Assembles and validates the Building Schema JSON that is the primary
    data contract consumed by Components 02, 03, and 04.
    """

    def __init__(self) -> None:
        schema_dir = Path(os.getenv("SCHEMA_DIR", "shared/schemas"))
        schema_path = schema_dir / "building_schema.json"
        if schema_path.exists():
            with schema_path.open("r", encoding="utf-8") as fh:
                self.schema: dict | None = json.load(fh)
            _logger.info("Loaded building_schema.json from %s", schema_path)
        else:
            _logger.warning(
                "building_schema.json not found at %s — validation skipped", schema_path
            )
            self.schema = None

        self.c02_url: str = os.getenv("C02_BASE_URL", "") + "/estimate"

    def serialise(
        self,
        floor_plan: dict,
        site_schema: dict,
        buildable_zone: dict,
        user_requirements: dict,
    ) -> dict:
        """Assembles and validates the Building Schema for Component 02.

        Args:
            floor_plan: Approved floor plan from Stage 3.
            site_schema: Stage 1 validated site schema.
            buildable_zone: Stage 2 buildable zone result.
            user_requirements: User form input dict.

        Returns:
            dict: Validated Building Schema conforming to building_schema.json.

        Raises:
            jsonschema.ValidationError: If assembled schema fails validation
                against building_schema.json.
        """
        style = user_requirements.get("style", "modern")
        budget_tier = user_requirements.get("budget_tier", "medium")
        is_coastal = site_schema.get("is_coastal", False)
        area_sqm = site_schema.get("area_sqm", 0)

        finish_grade = _BUDGET_TO_FINISH.get(budget_tier, "medium")
        roof_type = _STYLE_TO_ROOF.get(style, "gable")

        if is_coastal:
            foundation_type = "pile"
        elif area_sqm > 500:
            foundation_type = "raft"
        else:
            foundation_type = "strip"

        rooms = floor_plan.get("rooms", [])

        building_schema = {
            "schema_version": "1.0.0",
            "plan_id": site_schema.get("plan_id", "PLAN-UNKNOWN"),
            "district": site_schema.get("district"),
            "is_coastal": is_coastal,
            "site": {
                "area_sqm": site_schema.get("area_sqm"),
                "boundary_polygon": site_schema.get("boundary_polygon", []),
                "road_access": site_schema.get("road_access"),
                "orientation_degrees": site_schema.get("orientation_degrees", 0.0),
            },
            "buildable_zone": {
                "max_footprint_sqm": buildable_zone.get("max_footprint_sqm"),
                "max_total_built_sqm": buildable_zone.get("max_total_built_sqm"),
                "coverage_achieved": buildable_zone.get("coverage_achieved"),
                "setback_margins": buildable_zone.get("setback_margins", {}),
            },
            "building": {
                "floors": user_requirements.get("floors", 1),
                "total_built_sqm": floor_plan.get("total_area_sqm"),
                "finish_grade": finish_grade,
                "roof_type": roof_type,
                "foundation_type": foundation_type,
                "architectural_style": style,
                "has_garage": user_requirements.get("garage", False),
            },
            "rooms": [
                {
                    "name": r.get("name"),
                    "area_sqm": r.get("area_sqm"),
                    "floor": r.get("floor", 1),
                    "window_orientation": r.get("window_orientation"),
                    "adjacencies": r.get("adjacencies", []),
                    "position": {
                        "x_norm": r.get("x_norm"),
                        "y_norm": r.get("y_norm"),
                        "width_norm": r.get("width_norm"),
                        "height_norm": r.get("height_norm"),
                    },
                }
                for r in rooms
            ],
            "layout_label": floor_plan.get("layout_label", "balanced"),
            "quality_scores": floor_plan.get("quality_scores", {}),
        }

        if self.schema is not None:
            try:
                jsonschema.validate(instance=building_schema, schema=self.schema)
                _logger.info(
                    "Building schema validation passed for %s",
                    building_schema["plan_id"],
                )
            except jsonschema.ValidationError as exc:
                _logger.error(
                    "Building schema validation failed — path=%s, message=%s",
                    list(exc.absolute_path),
                    exc.message,
                )
                raise
        else:
            _logger.warning(
                "Skipping building schema validation (schema file not loaded)"
            )

        self._post_to_c02(building_schema)
        return building_schema

    def _post_to_c02(self, building_schema: dict) -> None:
        """Fire-and-forget HTTP POST to Component 02 /estimate endpoint.

        Never raises — rendering must not be blocked by C02 availability.
        """
        if not self.c02_url or self.c02_url == "/estimate":
            _logger.info("C02_BASE_URL not configured — skipping C02 integration")
            return

        try:
            import httpx

            with httpx.Client(timeout=10.0) as client:
                response = client.post(self.c02_url, json=building_schema)
            _logger.info(
                "C02 integration: POST %s → HTTP %d", self.c02_url, response.status_code
            )
        except Exception as exc:
            _logger.warning("C02 integration failed (non-blocking): %s", exc)
