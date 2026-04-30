"""Assembles OCR, boundary, and NER outputs into a validated Site Schema."""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import jsonschema
from shapely.geometry import Polygon

from utils.logger import get_logger

_logger = get_logger("schema_assembler")

_ROAD_ACCESS_MAP = {
    "national road": "national_road",
    "main road": "national_road",
    "provincial road": "provincial",
    "lane": "lane",
    "slpa road": "local",
    "grama": "local",
}


class SchemaAssembler:
    """Assembles and validates the Site Schema from Stage 1 pipeline outputs."""

    def __init__(self) -> None:
        schema_dir = Path(os.getenv("SCHEMA_DIR", "shared/schemas"))
        schema_path = schema_dir / "site_schema.json"
        if schema_path.exists():
            with schema_path.open("r", encoding="utf-8") as fh:
                self.schema: Optional[dict] = json.load(fh)
            _logger.info("Loaded site_schema.json from %s", schema_path)
        else:
            _logger.warning("site_schema.json not found at %s — validation skipped", schema_path)
            self.schema = None

    def _compute_orientation(self, polygon: list) -> float:
        """Computes dominant orientation of the plot boundary in degrees from north.

        Args:
            polygon: List of [x, y] normalised coordinate pairs.

        Returns:
            float: Bearing in degrees (0 = north, 90 = east).
        """
        if len(polygon) < 3:
            return 0.0

        try:
            shapely_poly = Polygon(polygon)
            rect = shapely_poly.minimum_rotated_rectangle
            coords = list(rect.exterior.coords)
            dx = coords[1][0] - coords[0][0]
            dy = coords[1][1] - coords[0][1]
            import math
            angle = math.degrees(math.atan2(dy, dx)) % 360
            return round(angle, 2)
        except Exception:
            # TODO Sprint 4: use actual coordinate system (CRS) for bearing
            return 0.0

    def _compute_frontage(self, polygon: list, road_access_side: str) -> float:
        """Estimates frontage width from polygon bounding box.

        Args:
            polygon: List of [x, y] normalised coordinate pairs.
            road_access_side: Road access direction string.

        Returns:
            float: Conservative frontage estimate (shorter bounding dimension).
        """
        if len(polygon) < 3:
            return 0.0

        try:
            shapely_poly = Polygon(polygon)
            minx, miny, maxx, maxy = shapely_poly.bounds
            width = maxx - minx
            height = maxy - miny
            # TODO Sprint 4: use actual coordinate system for accurate frontage
            return round(min(width, height), 4)
        except Exception:
            return 0.0

    def assemble(self, ocr_result: dict, polygon: list, ner_result: dict) -> dict:
        """Assembles OCR tokens, boundary polygon, and NER fields into a validated
        Site Schema.

        Args:
            ocr_result: Output from OCREngine.extract_text().
            polygon: Output from BoundaryDetector.detect_polygon().
            ner_result: Output from NERParser.parse().

        Returns:
            dict: Validated Site Schema conforming to site_schema.json.

        Raises:
            jsonschema.ValidationError: If assembled schema fails validation.
            ValueError: If required fields (area_sqm, district) cannot be extracted.
        """
        if ner_result.get("area_sqm") is None:
            raise ValueError(
                "Could not extract plot area from cadastral plan. "
                "Ensure the scan contains a legible area annotation."
            )
        if ner_result.get("district") is None:
            raise ValueError(
                "Could not extract district from cadastral plan. "
                "Ensure the district name is visible in the scan."
            )

        plan_number = ner_result.get("plan_number") or "UNKNOWN"
        district_code = (ner_result.get("district") or "XX").replace(" ", "")[:2].upper()
        plan_id = f"PLAN-{plan_number}-{district_code}-{datetime.now().strftime('%Y%m%d')}"

        raw_road = (ner_result.get("road_access") or "").lower()
        road_type = "local"
        for key, value in _ROAD_ACCESS_MAP.items():
            if key in raw_road:
                road_type = value
                break

        orientation_deg = self._compute_orientation(polygon)
        frontage_m = self._compute_frontage(polygon, road_type)

        site_schema = {
            "plan_id": plan_id,
            "plan_number": ner_result.get("plan_number"),
            "district": ner_result["district"],
            "province": ner_result.get("province"),
            "area_sqm": ner_result["area_sqm"],
            "scale": ner_result.get("scale"),
            "surveyor": ner_result.get("surveyor"),
            "lot_number": ner_result.get("lot_number"),
            "road_access": road_type,
            "is_coastal": ner_result.get("is_coastal", False),
            "orientation_degrees": orientation_deg,
            "frontage_m": frontage_m,
            "boundary_polygon": polygon,
            "page_dimensions": ocr_result.get("page_dimensions", {}),
            "coordinate_n": ner_result.get("coordinate_n"),
            "coordinate_e": ner_result.get("coordinate_e"),
            "licence_number": ner_result.get("licence_number"),
        }

        if self.schema is not None:
            try:
                jsonschema.validate(instance=site_schema, schema=self.schema)
                _logger.info("Site schema validation passed for %s", plan_id)
            except jsonschema.ValidationError as exc:
                _logger.error(
                    "Site schema validation failed — path=%s, message=%s",
                    list(exc.absolute_path),
                    exc.message,
                )
                raise
        else:
            _logger.warning(
                "Skipping schema validation (schema file not loaded) for %s", plan_id
            )

        return site_schema
