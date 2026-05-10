"""Strip-packing layout solver that eliminates room overlaps in LLM-generated floor plans."""

import copy
from collections import defaultdict

from utils.logger import get_logger

_logger = get_logger("layout_solver")


def _pack_floor(rooms: list[dict]) -> list[dict]:
    """Repositions rooms for one floor using strip packing so none overlap."""
    rooms = [copy.copy(r) for r in rooms]

    for r in rooms:
        r["width_norm"] = max(float(r.get("width_norm", 0.1)), 0.05)
        r["height_norm"] = max(float(r.get("height_norm", 0.1)), 0.05)

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
        room["width_norm"] = w
        current_row.append(room)
        current_width += w

    if current_row:
        rows.append(current_row)

    # Scale widths within each row to fill exactly [0, 1]
    for row in rows:
        total_w = sum(r["width_norm"] for r in row)
        scale = 1.0 / total_w if total_w > 0 else 1.0
        x = 0.0
        for room in row:
            room["width_norm"] = round(room["width_norm"] * scale, 4)
            room["x_norm"] = round(x, 4)
            x += room["width_norm"]

    row_heights = [max(r["height_norm"] for r in row) for row in rows]
    total_h = sum(row_heights)
    h_scale = 1.0 / total_h if total_h > 1.0 else 1.0

    y = 0.0
    result = []
    for row, rh in zip(rows, row_heights):
        scaled_rh = round(rh * h_scale, 4)
        for room in row:
            room["y_norm"] = round(y, 4)
            room["height_norm"] = round(room["height_norm"] * h_scale, 4)
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

    by_floor: dict[int, list[dict]] = defaultdict(list)
    for room in rooms:
        by_floor[int(room.get("floor", 1))].append(room)

    solved_rooms: list[dict] = []
    for floor_num in sorted(by_floor):
        packed = _pack_floor(by_floor[floor_num])  # positions in [0, 1]
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
