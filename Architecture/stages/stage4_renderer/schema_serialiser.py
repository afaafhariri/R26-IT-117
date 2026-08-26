"""Assembles and validates the Building Schema JSON for Component 02 handoff.

The output format matches the flat JSON contract agreed with the Cost Estimation
model (Component 02) as documented in the Architecture Model workflow specification.

Fields derived from geometry, plan data, and floor plan are computed here so that
Component 02 receives everything it needs for material quantity and cost estimation.
"""

import json
import math
import os
from datetime import date
from pathlib import Path

import jsonschema

from utils.logger import get_logger

_logger = get_logger("schema_serialiser")

# ── Lookup tables ──────────────────────────────────────────────────────────────

_BUDGET_TO_FINISH: dict[str, str] = {
    "economy": "economy",
    "medium":  "mid",       # C02 contract uses "mid" not "medium"
    "luxury":  "luxury",
}

_STYLE_TO_ROOF: dict[str, str] = {
    "modern":        "flat",
    "traditional":   "hip",
    "contemporary":  "gable",
}

# NBC road type → C02 road_access surface type
_ROAD_TO_ACCESS: dict[str, str] = {
    "national_road": "paved",
    "provincial":    "paved",
    "local":         "paved",
    "lane":          "gravel",
}

# Foundation excavation depths (metres)
_FOUNDATION_DEPTH: dict[str, float] = {
    "pile":  2.5,
    "raft":  1.8,
    "strip": 1.5,
}

# Room types that are NOT counted in room_count (wet/utility/parking rooms)
_EXCLUDED_FROM_ROOM_COUNT = {"bathroom", "garage", "utility", "store", "storeroom"}

# Room types whose names get normalised to a base key for the rooms-count dict
_ROOM_BASE_ALIASES: dict[str, str] = {
    "master bedroom": "master_bedroom",
    "master_bedroom": "master_bedroom",
    "living room":    "living_room",
    "living_room":    "living_room",
    "dining room":    "dining_room",
    "dining_room":    "dining_room",
    "bed room":       "bedroom",
}


# ── Geometry helpers ───────────────────────────────────────────────────────────

def _estimate_perimeter(footprint_sqm: float) -> float:
    """Estimates outer wall perimeter from footprint area.

    Assumes a typical 1.4 : 1 aspect ratio (common in Sri Lankan detached
    dwellings). For a square: perimeter = 4 * sqrt(A). The 1.4 ratio gives a
    slightly longer rectangle, which is more realistic.
    """
    if footprint_sqm <= 0:
        return 0.0
    width  = math.sqrt(footprint_sqm / 1.4)
    height = footprint_sqm / width
    return round(2 * (width + height), 1)


def _estimate_column_count(footprint_sqm: float, floors: int) -> int:
    """Estimates structural RC column count from footprint and floors.

    Columns are placed on a ~3.5 m grid for standard residential construction.
    Multi-storey buildings add extra columns at mid-span points.
    """
    if footprint_sqm <= 0:
        return 4
    side = math.sqrt(footprint_sqm)
    cols_per_side = max(2, round(side / 3.5) + 1)
    base_count = cols_per_side * cols_per_side
    # Additional intermediate columns for 2+ storey
    return base_count + (max(0, floors - 1) * 2)


def _estimate_openings_sqm(rooms: list) -> float:
    """Estimates total area of openings (doors + windows) from room list.

    Rules applied:
    - 1 door per room @ 0.9 m × 2.1 m = 1.89 sqm each
    - 2 windows per habitable room @ 1.2 m × 1.0 m = 1.2 sqm each
    - 1 window per wet/service room @ 0.6 m × 0.9 m = 0.54 sqm each
    """
    _HABITABLE = {"bedroom", "master_bedroom", "living_room", "dining", "dining_room", "study"}
    door_area = len(rooms) * 1.89
    window_area = 0.0
    for r in rooms:
        name = r.get("name", "").lower().replace(" ", "_")
        is_habitable = any(name.startswith(h) for h in _HABITABLE)
        window_area += 2 * 1.2 if is_habitable else 0.54
    return round(door_area + window_area, 1)


def _estimate_internal_wall_length(rooms: list) -> float:
    """Estimates total internal partition wall length from room areas.

    Each room is approximated as a rectangle; the sum of its two shorter edges
    represents internal partitions. A 0.65 factor accounts for shared walls
    counted only once.
    """
    total = 0.0
    for r in rooms:
        area = r.get("area_sqm", 0)
        if area > 0:
            # shorter side of a ~1.3:1 rectangle
            short = math.sqrt(area / 1.3)
            long  = area / short
            total += short + long   # one shared wall contribution per room
    return round(total * 0.65, 1)


def _rooms_as_counts(rooms: list) -> dict:
    """Converts the rooms array into a {room_type: count} dict for C02.

    Numbered variants (bedroom_1, bedroom_2) are folded into their base type.
    """
    counts: dict[str, int] = {}
    for r in rooms:
        raw = r.get("name", "").lower().strip()
        # Normalise spaces → underscores
        key = raw.replace(" ", "_")
        # Alias known variants
        key = _ROOM_BASE_ALIASES.get(key, key)
        # Strip trailing numeric suffix: bedroom_2 → bedroom
        import re as _re
        key = _re.sub(r"_\d+$", "", key)
        counts[key] = counts.get(key, 0) + 1
    return counts


# ── Main class ─────────────────────────────────────────────────────────────────

class SchemaSerialiser:
    """Assembles the Building Schema JSON that is the primary data contract
    consumed by Component 02 (Cost Estimation), Component 03 (Timeline), and
    Component 04 (Frontend).

    Output format matches the flat JSON specification in the Architecture Model
    workflow document.
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
        """Assembles the flat Building Schema JSON for Component 02.

        Args:
            floor_plan: Approved floor plan from Stage 3 (with rooms list).
            site_schema: Stage 1 validated site schema.
            buildable_zone: Stage 2 buildable zone result.
            user_requirements: User form input dict.

        Returns:
            dict: Building Schema conforming to the C02 flat JSON contract.

        Raises:
            jsonschema.ValidationError: If building_schema.json is loaded and
                the assembled schema fails validation.
        """
        # ── Source values ──────────────────────────────────────────────────────
        style        = user_requirements.get("style", "modern")
        budget_tier  = user_requirements.get("budget_tier", "medium")
        floors       = int(user_requirements.get("floors", 1))
        is_coastal   = bool(site_schema.get("is_coastal", False))
        area_sqm     = float(site_schema.get("area_sqm") or 0)
        district     = site_schema.get("district", "")
        province     = site_schema.get("province") or ""
        road_raw     = site_schema.get("road_access", "local")
        terrain      = user_requirements.get("terrain", "flat")
        target_date  = user_requirements.get(
            "target_date",
            date.today().replace(year=date.today().year + 1).isoformat(),
        )

        footprint_sqm = float(buildable_zone.get("max_footprint_sqm") or 0)
        rooms: list[dict] = floor_plan.get("rooms", [])

        # ── Derived values ─────────────────────────────────────────────────────
        finish_grade = _BUDGET_TO_FINISH.get(budget_tier, "mid")
        roof_type    = _STYLE_TO_ROOF.get(style, "gable")

        if is_coastal:
            foundation_type = "pile"
        elif area_sqm > 500:
            foundation_type = "raft"
        else:
            foundation_type = "strip"

        road_access      = _ROAD_TO_ACCESS.get(road_raw, "paved")
        perimeter        = _estimate_perimeter(footprint_sqm)
        excavation_depth = _FOUNDATION_DEPTH[foundation_type]
        column_count     = _estimate_column_count(footprint_sqm, floors)
        openings_sqm     = _estimate_openings_sqm(rooms)
        internal_wall_len= _estimate_internal_wall_length(rooms)
        rooms_counts     = _rooms_as_counts(rooms)

        bathroom_count = rooms_counts.get("bathroom", 0)
        room_count = sum(
            v for k, v in rooms_counts.items()
            if not any(k.startswith(ex) for ex in _EXCLUDED_FROM_ROOM_COUNT)
        )

        # ── Flat JSON contract (matches C02 specification exactly) ─────────────
        building_schema = {
            # ── Geometry ──
            "footprint_sqm":       round(footprint_sqm, 2),
            "perimeter":           perimeter,
            "floors":              floors,
            "floor_height":        3.0,
            "wall_height":         3.0,
            "excavation_depth":    excavation_depth,
            # ── Structure ──
            "column_count":        column_count,
            "openings_sqm":        openings_sqm,
            "internal_wall_length": internal_wall_len,
            # ── Finish ──
            "finish_grade":        finish_grade,
            "roof_type":           roof_type,
            # ── Location / environment ──
            "district":            district,
            "province":            province,
            "is_coastal":          is_coastal,
            "terrain":             terrain,
            "road_access":         road_access,
            "plot_area":           round(area_sqm, 2),
            # ── Rooms ──
            "rooms":               rooms_counts,
            "bathroom_count":      bathroom_count,
            "room_count":          room_count,
            # ── Time / cost indexing ──
            "base_rate_date":      date.today().isoformat(),
            "target_date":         target_date,
            # ── Metadata (informational, not used by C02) ──
            "_meta": {
                "plan_id":        site_schema.get("plan_id", "PLAN-UNKNOWN"),
                "layout_label":   floor_plan.get("layout_label", "balanced"),
                "quality_scores": floor_plan.get("quality_scores", {}),
                "foundation_type": foundation_type,
                "total_built_sqm": floor_plan.get("total_area_sqm"),
                "coverage_achieved": buildable_zone.get("coverage_achieved"),
                "setback_margins": buildable_zone.get("setback_margins", {}),
                "gps_lat":        site_schema.get("gps_lat"),
                "gps_lon":        site_schema.get("gps_lon"),
            },
        }

        _logger.info(
            "Building schema assembled: plan_id=%s, footprint=%.1f sqm, "
            "floors=%d, rooms=%d, columns=%d, perimeter=%.1f m",
            building_schema["_meta"]["plan_id"],
            footprint_sqm,
            floors,
            len(rooms),
            column_count,
            perimeter,
        )

        if self.schema is not None:
            try:
                jsonschema.validate(instance=building_schema, schema=self.schema)
                _logger.info(
                    "Building schema validation passed for %s",
                    building_schema["_meta"]["plan_id"],
                )
            except jsonschema.ValidationError as exc:
                _logger.error(
                    "Building schema validation failed — path=%s, message=%s",
                    list(exc.absolute_path),
                    exc.message,
                )
                raise
        else:
            _logger.warning("Skipping building schema validation (schema file not loaded)")

        self._post_to_c02(building_schema)
        return building_schema

    def _post_to_c02(self, building_schema: dict) -> None:
        """Fire-and-forget HTTP POST to Component 02 /estimate endpoint.

        Strips the _meta key before sending so C02 receives only the fields
        it expects. Never raises — rendering must not be blocked by C02 availability.
        """
        if not self.c02_url or self.c02_url == "/estimate":
            _logger.info("C02_BASE_URL not configured — skipping C02 integration")
            return

        try:
            import httpx

            payload = {k: v for k, v in building_schema.items() if k != "_meta"}
            with httpx.Client(timeout=10.0) as client:
                response = client.post(self.c02_url, json=payload)
            _logger.info(
                "C02 integration: POST %s → HTTP %d", self.c02_url, response.status_code
            )
        except Exception as exc:
            _logger.warning("C02 integration failed (non-blocking): %s", exc)
