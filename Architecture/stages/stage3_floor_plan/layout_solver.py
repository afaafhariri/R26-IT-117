"""Strip-packing layout solver that eliminates room overlaps in LLM-generated floor plans."""

import copy
import math
from collections import defaultdict

from stages.stage3_floor_plan.prompt_builder import _MIN_ROOM_SQM
from utils.logger import get_logger

_logger = get_logger("layout_solver")

_SQM_TO_SQFT = 10.7639
_DEFAULT_MIN_ROOM_SQM = 8.0


def _room_key(name: str) -> str:
    """Maps a generated room name (e.g. 'bedroom_2', 'bathroom_2') to its
    NBC minimum-size lookup key (e.g. 'bedroom', 'bathroom')."""
    key = name.lower().replace(" ", "_")
    for k in _MIN_ROOM_SQM:
        if key.startswith(k):
            return k
    return ""


def _min_norm_dims(name: str, zone_w: float, zone_h: float, dim_ft: float) -> tuple[float, float]:
    """Minimum (width_norm, height_norm) in the local [0,1] packing space for
    a room type, derived from its real NBC minimum area (same source of truth
    used to build the LLM prompt). Enforcing this *before* packing — instead
    of inflating room sizes after positions are already assigned — is what
    keeps the packed layout overlap-free: the packer never has to deal with
    a room that's smaller than this, so it never places two rooms closer
    together than their real minimum sizes allow.
    """
    min_sqm = _MIN_ROOM_SQM.get(_room_key(name), _DEFAULT_MIN_ROOM_SQM)
    min_sqft = min_sqm * _SQM_TO_SQFT
    # ~1.2:1 width:height, matching prompt_builder's target-size guidance
    min_width_ft = math.sqrt(min_sqft * 1.2)
    min_height_ft = math.sqrt(min_sqft / 1.2)
    scale_x = zone_w * dim_ft if zone_w * dim_ft > 0 else 1.0
    scale_y = zone_h * dim_ft if zone_h * dim_ft > 0 else 1.0
    return min_width_ft / scale_x, min_height_ft / scale_y


def _pack_floor(rooms: list[dict], zone_w: float, zone_h: float, dim_ft: float) -> list[dict]:
    """Repositions rooms for one floor using strip packing so none overlap."""
    rooms = [copy.copy(r) for r in rooms]

    for r in rooms:
        min_w, min_h = _min_norm_dims(r.get("name", ""), zone_w, zone_h, dim_ft)
        r["width_norm"] = max(float(r.get("width_norm", min_w)), min_w)
        r["height_norm"] = max(float(r.get("height_norm", min_h)), min_h)

    rooms.sort(key=lambda r: r["height_norm"], reverse=True)

    rows: list[list[dict]] = []
    current_row: list[dict] = []
    current_width = 0.0

    for room in rooms:
        w = min(room["width_norm"], 1.0)
        if current_row and current_width + w > 1.0 + 1e-9:
            rows.append(current_row)
            current_row = []
            current_width = 0.0
        # If the room alone is wider than 1.0, cap it at the full zone width
        w = min(w, 1.0)
        room["width_norm"] = w
        current_row.append(room)
        current_width += w

    if current_row:
        rows.append(current_row)

    # Assign x positions left-to-right WITHOUT stretching widths.
    # Preserving Gemini's width_norm keeps room sizes realistic — rows
    # do not need to fill the full [0, 1] width.
    # No intermediate rounding here (or below) — rounding at each step and
    # then accumulating (y += previous row's *rounded* height) compounds
    # drift across many rows, which was enough to reopen tiny overlaps
    # between rooms that should sit flush against each other. Round once,
    # at the very end, in solve_overlaps's remap step instead.
    for row in rows:
        x = 0.0
        for room in row:
            room["x_norm"] = x
            x += room["width_norm"]

    row_heights = [max(r["height_norm"] for r in row) for row in rows]
    total_h = sum(row_heights)
    # Scale rows to fill [0,1] when there's spare vertical space (total_h < 1) —
    # but never scale *down* below 1:1. Shrinking would push rooms below the
    # minimum sizes just enforced above, which packing then can't guarantee
    # stays overlap-free. If the rooms genuinely need more height than the
    # nominal zone (too many rows to fit minimum-sized rooms side by side),
    # let the packed layout extend past the nominal zone height instead —
    # a room slightly outside the drawn zone is a lesser problem than rooms
    # visibly overlapping each other.
    h_scale = 1.0 / total_h if 0 < total_h < 1.0 else 1.0

    y = 0.0
    result = []
    for row, rh in zip(rows, row_heights):
        scaled_rh = rh * h_scale
        for room in row:
            room["y_norm"] = y
            room["height_norm"] = room["height_norm"] * h_scale
        y += scaled_rh
        result.extend(row)

    return result


def solve_overlaps(floor_plan: dict, buildable_zone: dict | None = None) -> dict:
    """Repositions all rooms in a floor plan to eliminate geometric overlaps.

    Preserves room names, areas, adjacencies, and window orientations.
    Only x_norm, y_norm, width_norm, height_norm are modified.
    Rooms are placed within the buildable zone bounds so they pass zone containment checks.

    Args:
        floor_plan: Dict from LLM generator containing a 'rooms' list.
        buildable_zone: Stage 2 output used to determine valid placement bounds.

    Returns:
        dict: Updated floor plan with non-overlapping room positions inside the zone.
    """
    rooms: list[dict] = floor_plan.get("rooms", [])
    if not rooms:
        return floor_plan

    # Compute zone bounding box for placement
    coords = (buildable_zone or {}).get("buildable_polygon", [])
    if coords and len(coords) >= 3:
        xs = [p[0] for p in coords]
        ys = [p[1] for p in coords]
        zone_x0, zone_x1 = min(xs), max(xs)
        zone_y0, zone_y1 = min(ys), max(ys)
    else:
        zone_x0, zone_x1, zone_y0, zone_y1 = 0.0, 1.0, 0.0, 1.0

    zone_w = zone_x1 - zone_x0
    zone_h = zone_y1 - zone_y0

    # Real-world scale, so NBC minimum room sizes (in sqm) can be converted
    # into this floor's local normalized packing space before packing runs.
    buildable_sqft = float((buildable_zone or {}).get("buildable_area_sqft") or 1000)
    dim_ft = math.sqrt(buildable_sqft) if buildable_sqft > 0 else 30.0

    by_floor: dict[int, list[dict]] = defaultdict(list)
    for room in rooms:
        by_floor[int(room.get("floor", 1))].append(room)

    solved_rooms: list[dict] = []
    for floor_num in sorted(by_floor):
        packed = _pack_floor(by_floor[floor_num], zone_w, zone_h, dim_ft)  # positions in [0, 1]
        # Remap from [0,1] into the actual buildable zone bounds
        for room in packed:
            room["x_norm"] = round(zone_x0 + room["x_norm"] * zone_w, 4)
            room["y_norm"] = round(zone_y0 + room["y_norm"] * zone_h, 4)
            room["width_norm"] = round(room["width_norm"] * zone_w, 4)
            room["height_norm"] = round(room["height_norm"] * zone_h, 4)
        solved_rooms.extend(packed)

    result = dict(floor_plan)
    result["rooms"] = solved_rooms
    _logger.info(
        "Layout solver repositioned %d rooms across %d floor(s) within zone [%.2f,%.2f]–[%.2f,%.2f]",
        len(solved_rooms), len(by_floor), zone_x0, zone_y0, zone_x1, zone_y1,
    )
    return result
