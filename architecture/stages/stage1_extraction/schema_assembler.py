"""
schema_assembler.py — Assembles and validates the Stage 1 Site Schema.

Combines OCR tokens, polygon coordinates, and NER-extracted fields
into a single validated Site Schema JSON document.
"""

import uuid
import math
import logging
from typing import Any

import jsonschema

logger = logging.getLogger(__name__)

# ── JSON Schema for Site Schema output ───────────────────────────────────────

SITE_SCHEMA = {
    "type": "object",
    "required": ["plan_id", "site", "boundaries"],
    "properties": {
        "plan_id": {"type": "string"},
        "site": {
            "type": "object",
            "required": ["plot_area_sqm", "district", "is_coastal", "terrain", "road_access"],
            "properties": {
                "plot_area_sqm": {"type": "number", "minimum": 0},
                "district": {"type": "string"},
                "is_coastal": {"type": "boolean"},
                "terrain": {"type": "string"},
                "road_access": {"type": "string"},
            },
        },
        "boundaries": {
            "type": "object",
            "required": ["polygon", "orientation_degrees", "frontage_width_m"],
            "properties": {
                "polygon": {
                    "type": "array",
                    "items": {
                        "type": "array",
                        "items": {"type": "number"},
                        "minItems": 2,
                        "maxItems": 2,
                    },
                    "minItems": 3,
                },
                "orientation_degrees": {"type": "number"},
                "frontage_width_m": {"type": "number", "minimum": 0},
            },
        },
    },
    "additionalProperties": True,
}

# Sri Lankan coastal districts — used for is_coastal heuristic
_COASTAL_DISTRICTS = frozenset(
    {
        "colombo", "gampaha", "kalutara", "galle", "matara", "hambantota",
        "puttalam", "mannar", "jaffna", "kilinochchi", "mullaitivu",
        "trincomalee", "batticaloa", "ampara",
    }
)


class SchemaAssembler:
    """Combines extraction results into a validated Site Schema JSON."""

    def assemble(self, ocr: dict, polygon: list, ner: dict) -> dict:
        """
        Build and validate the Site Schema.

        Args:
            ocr:     Output of OCREngine.extract_text().
            polygon: Output of BoundaryDetector.detect_polygon() —
                     list of [x, y] pixel coordinates.
            ner:     Output of NERParser.parse().

        Returns:
            Validated Site Schema dict conforming to SITE_SCHEMA.

        Raises:
            ValueError: If the assembled schema fails jsonschema validation.
        """
        district = (ner.get("district") or "unknown").lower()
        area_sqm = ner.get("area_sqm") or self._estimate_area_from_polygon(polygon)
        orientation = self._compute_orientation(polygon)
        frontage = self._compute_frontage(polygon)

        schema: dict[str, Any] = {
            "plan_id": ner.get("plan_number") or str(uuid.uuid4()),
            "site": {
                "plot_area_sqm": round(area_sqm, 2),
                "district": district.title(),
                "is_coastal": district in _COASTAL_DISTRICTS,
                "terrain": "flat",  # TODO: derive from elevation data or user input
                "road_access": ner.get("road_access") or "local",
            },
            "boundaries": {
                "polygon": polygon,
                "orientation_degrees": round(orientation, 2),
                "frontage_width_m": round(frontage, 2),
            },
            # Carry through auxiliary fields for downstream stages
            "meta": {
                "lot_number": ner.get("lot_number"),
                "surveyor": ner.get("surveyor"),
                "scale": ner.get("scale"),
                "ocr_token_count": len(ocr.get("tokens", [])),
            },
        }

        self._validate(schema)
        return schema

    # ── Private helpers ───────────────────────────────────────────────────

    def _validate(self, schema: dict) -> None:
        """Raise ValueError with details if schema does not conform."""
        try:
            jsonschema.validate(instance=schema, schema=SITE_SCHEMA)
        except jsonschema.ValidationError as exc:
            raise ValueError(f"Site Schema validation failed: {exc.message}") from exc

    @staticmethod
    def _estimate_area_from_polygon(polygon: list) -> float:
        """
        Compute polygon area using the Shoelace formula (pixel space).
        TODO: apply scale factor to convert pixels² → metres².
        """
        if len(polygon) < 3:
            return 0.0
        n = len(polygon)
        area = 0.0
        for i in range(n):
            x1, y1 = polygon[i]
            x2, y2 = polygon[(i + 1) % n]
            area += x1 * y2 - x2 * y1
        return abs(area) / 2.0

    @staticmethod
    def _compute_orientation(polygon: list) -> float:
        """
        Estimate the primary orientation of the plot from its longest edge.
        Returns angle in degrees clockwise from North (0°).
        TODO: calibrate to True North using cadastral magnetic declination data.
        """
        if len(polygon) < 2:
            return 0.0

        max_len = 0.0
        angle = 0.0
        n = len(polygon)
        for i in range(n):
            x1, y1 = polygon[i]
            x2, y2 = polygon[(i + 1) % n]
            length = math.hypot(x2 - x1, y2 - y1)
            if length > max_len:
                max_len = length
                angle = math.degrees(math.atan2(y2 - y1, x2 - x1)) % 360
        return angle

    @staticmethod
    def _compute_frontage(polygon: list) -> float:
        """
        Estimate road frontage width as the shortest edge of the polygon.
        TODO: identify road-facing edge using road proximity data.
        """
        if len(polygon) < 2:
            return 0.0
        n = len(polygon)
        edges = []
        for i in range(n):
            x1, y1 = polygon[i]
            x2, y2 = polygon[(i + 1) % n]
            edges.append(math.hypot(x2 - x1, y2 - y1))
        return min(edges) if edges else 0.0
