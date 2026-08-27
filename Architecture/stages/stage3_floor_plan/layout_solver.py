"""Strip-packing layout solver that eliminates room overlaps in LLM-generated floor plans."""

import copy
import math
from collections import defaultdict

from shapely.geometry import Polygon, box as shapely_box

from stages.stage3_floor_plan.prompt_builder import _MIN_ROOM_SQM, _compute_target_sizes, parse_entrance_side
from utils.logger import get_logger

_logger = get_logger("layout_solver")

_SQM_TO_SQFT = 10.7639
_DEFAULT_MIN_ROOM_SQM = 8.0
_INSCRIBED_RECT_GRID = 20


def _room_key(name: str) -> str:
    """Maps a generated room name (e.g. 'bedroom_2', 'bathroom_2') to its
    NBC minimum-size lookup key (e.g. 'bedroom', 'bathroom')."""
    key = name.lower().replace(" ", "_")
    for k in _MIN_ROOM_SQM:
        if key.startswith(k):
            return k
    return ""


def _sqm_to_norm_dims(sqm: float, zone_w: float, zone_h: float, dim_ft: float) -> tuple[float, float]:
    """Converts a target area (sqm) to (width_norm, height_norm) in the local
    [0,1] packing space, at the ~1.2:1 width:height ratio used throughout
    Stage 3."""
    sqft = sqm * _SQM_TO_SQFT
    width_ft = math.sqrt(sqft * 1.2)
    height_ft = math.sqrt(sqft / 1.2)
    scale_x = zone_w * dim_ft if zone_w * dim_ft > 0 else 1.0
    scale_y = zone_h * dim_ft if zone_h * dim_ft > 0 else 1.0
    return width_ft / scale_x, height_ft / scale_y


def _entrance_sort_key(room: dict, entrance_side: str) -> tuple:
    """Sort key that pulls living_room toward whichever end of the packing
    order lands it in the row/position closest to the real entrance side,
    instead of leaving its position to fall wherever a pure height-sort puts
    it. The row-based packer below fills rows top-to-bottom in processing
    order (north to south) and each row left-to-right (west to east), so
    processing living_room first lands it in the north/west-most position;
    processing it last lands it south/east-most. This only biases where
    living_room specifically ends up — every other room keeps the same
    relative order as before (tallest first), since only the row THAT
    contains living_room needs to be the entrance-adjacent one, not the
    whole layout reordered.
    """
    if _room_key(room.get("name", "")) != "living_room":
        return (1, -room["height_norm"])
    bias = 0 if entrance_side in ("north", "west") else 2
    return (bias, -room["height_norm"])


def _pack_floor(
    rooms: list[dict], zone_w: float, zone_h: float, dim_ft: float,
    y_offset: float = 0.0, entrance_side: str = "south",
) -> list[dict]:
    """Repositions rooms for one floor using strip packing so none overlap.

    Room sizes are grown from the legal NBC minimum toward a realistic target
    based on how much buildable land this floor actually has (same budget-
    scaling used to build the LLM prompt, via _compute_target_sizes) — a
    tight plot keeps rooms near minimum, a generous plot gets comfortably
    sized rooms, capped at a sensible per-room-type maximum. Sizes are set
    *before* packing (not after) for the same reason minimum-size enforcement
    used to work this way: growing a room in place after positions are
    already assigned would overlap its neighbors, which packing is supposed
    to eliminate.

    y_offset: fraction of the local [0,1] height reserved at the top of the
    zone for a fixed room solve_overlaps places separately (the staircase,
    on multi-floor plans) — these rooms pack into [y_offset, 1.0] instead of
    [0, 1.0], so nothing here can overlap that reserved space.
    """
    rooms = [copy.copy(r) for r in rooms]

    available_sqft = max(zone_w, 0.0) * max(zone_h, 0.0) * dim_ft * dim_ft
    available_sqm = available_sqft / _SQM_TO_SQFT
    room_types = [_room_key(r.get("name", "")) for r in rooms]
    target_sqm_by_type = _compute_target_sizes(room_types, available_sqm)

    for r, room_type in zip(rooms, room_types):
        target_sqm = target_sqm_by_type.get(
            room_type, _MIN_ROOM_SQM.get(room_type, _DEFAULT_MIN_ROOM_SQM)
        )
        target_w, target_h = _sqm_to_norm_dims(target_sqm, zone_w, zone_h, dim_ft)
        r["width_norm"] = max(float(r.get("width_norm", target_w)), target_w)
        r["height_norm"] = max(float(r.get("height_norm", target_h)), target_h)

    rooms.sort(key=lambda r: _entrance_sort_key(r, entrance_side))

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
    available_h = 1.0 - y_offset

    if total_h > available_h:
        # Rows need more height than the zone has. Rooms above were sized up
        # toward a budget target (not just their bare legal minimum), so
        # there's often slack to shrink back down without violating a
        # minimum — try that first, since overflowing the zone means these
        # rooms would fail zone-containment validation (the zone here is
        # already the largest rectangle that fits inside the true, possibly
        # irregular buildable polygon — there's no slack in the polygon
        # itself to give, only in how generously rooms were sized).
        shrink = available_h / total_h if total_h > 0 else 1.0
        for row in rows:
            for room in row:
                min_sqm = _MIN_ROOM_SQM.get(_room_key(room.get("name", "")), _DEFAULT_MIN_ROOM_SQM)
                _, min_h = _sqm_to_norm_dims(min_sqm, zone_w, zone_h, dim_ft)
                room["height_norm"] = max(room["height_norm"] * shrink, min_h)
        row_heights = [max(r["height_norm"] for r in row) for row in rows]
        total_h = sum(row_heights)
        # Still doesn't fit even with every room at its true minimum — there
        # is nothing left to shrink. Let the layout extend past the nominal
        # zone height rather than force rooms below minimum or overlap.
        h_scale = 1.0
    else:
        # Rooms come in under the available height — stretch to fill it
        # rather than leaving dead space at the bottom of the zone.
        h_scale = available_h / total_h if total_h > 0 else 1.0

    y = y_offset
    result = []
    for row, rh in zip(rows, row_heights):
        scaled_rh = rh * h_scale
        for room in row:
            room["y_norm"] = y
            room["height_norm"] = room["height_norm"] * h_scale
        y += scaled_rh
        result.extend(row)

    return result


def _largest_inscribed_rect(coords: list) -> tuple[float, float, float, float]:
    """Finds the largest axis-aligned rectangle fully contained within an
    arbitrary (possibly irregular) polygon, via grid search over candidate
    edges.

    Real cadastral plots are rarely perfect rectangles. Packing rooms into
    the polygon's raw bounding box can place them past the plot's true
    boundary wherever the box's corners stick out past an irregular shape —
    this is exactly what caused validator.py's "less than 95% within the
    buildable zone" failures. Packing into the largest rectangle that's
    actually inside the polygon guarantees every room stays within the true
    boundary, by construction, rather than relying on the packed layout
    happening to fit.

    Falls back to the raw bounding box if the polygon is invalid/degenerate
    or no contained rectangle is found (e.g. a very thin sliver shape) —
    both are rare edge cases and a bounding-box zone is the least-bad
    fallback available.
    """
    xs = [p[0] for p in coords]
    ys = [p[1] for p in coords]
    bbox = (min(xs), min(ys), max(xs), max(ys))

    try:
        poly = Polygon(coords)
        if not poly.is_valid or poly.area <= 0:
            return bbox
    except Exception:
        return bbox

    minx, miny, maxx, maxy = bbox
    n = _INSCRIBED_RECT_GRID
    xs_grid = [minx + (maxx - minx) * i / (n - 1) for i in range(n)]
    ys_grid = [miny + (maxy - miny) * i / (n - 1) for i in range(n)]

    best_area = 0.0
    best_rect = bbox
    for xi, x0 in enumerate(xs_grid):
        for x1 in xs_grid[xi + 1:]:
            width = x1 - x0
            if width * (maxy - miny) <= best_area:
                continue  # even the tallest possible rect at this width can't beat the best so far
            for yi, y0 in enumerate(ys_grid):
                for y1 in ys_grid[yi + 1:]:
                    area = width * (y1 - y0)
                    if area <= best_area:
                        continue
                    if poly.covers(shapely_box(x0, y0, x1, y1)):
                        best_area = area
                        best_rect = (x0, y0, x1, y1)

    return best_rect


def solve_overlaps(
    floor_plan: dict, buildable_zone: dict | None = None, orientation: str = "South-facing"
) -> dict:
    """Repositions all rooms in a floor plan to eliminate geometric overlaps.

    Preserves room names, areas, adjacencies, and window orientations.
    Only x_norm, y_norm, width_norm, height_norm are modified.
    Rooms are placed within the buildable zone bounds so they pass zone containment checks.

    Args:
        floor_plan: Dict from LLM generator containing a 'rooms' list.
        buildable_zone: Stage 2 output used to determine valid placement bounds.
        orientation: CadastralData.orientation string (e.g. "South-facing") —
            used to bias living_room toward the entrance-adjacent row/edge.
            The LLM prompt also carries this, but its own suggested room
            positions are discarded by this function (only room *size* is
            read from its output), so this is the only place that actually
            takes effect for entrance-aware placement.

    Returns:
        dict: Updated floor plan with non-overlapping room positions inside the zone.
    """
    rooms: list[dict] = floor_plan.get("rooms", [])
    if not rooms:
        return floor_plan

    entrance_side = parse_entrance_side(orientation)

    # Pack into the largest rectangle actually inscribed in the buildable
    # polygon — not its raw bounding box, which can extend past an irregular
    # plot's true boundary at the corners (see _largest_inscribed_rect).
    coords = (buildable_zone or {}).get("buildable_polygon", [])
    if coords and len(coords) >= 3:
        zone_x0, zone_y0, zone_x1, zone_y1 = _largest_inscribed_rect(coords)
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

    # A staircase must occupy the *same physical footprint* on every floor it
    # connects — it's a vertical shaft, not an independent room per floor.
    # The LLM generates one anyway (it doesn't know its position will be
    # overridden), but each floor's guess is unrelated to the others', so any
    # LLM-provided staircase entries are discarded and replaced with one
    # fixed-size, fixed-position instance reserved at the top of every floor,
    # in a strip other rooms are packed to avoid (see _pack_floor's y_offset).
    is_multi_floor = len(by_floor) > 1
    stair_w = stair_h = 0.0
    if is_multi_floor:
        stair_w, stair_h = _sqm_to_norm_dims(
            _MIN_ROOM_SQM["staircase"], zone_w, zone_h, dim_ft
        )
        # Safety clamp for a very small/narrow zone — never reserve so much
        # that other floor-1 rooms would have nowhere left to pack.
        stair_w = min(stair_w, 0.9)
        stair_h = min(stair_h, 0.5)

    solved_rooms: list[dict] = []
    for floor_num in sorted(by_floor):
        floor_rooms = [
            r for r in by_floor[floor_num]
            if _room_key(r.get("name", "")) != "staircase"
        ]
        packed = _pack_floor(
            floor_rooms, zone_w, zone_h, dim_ft,
            y_offset=stair_h if is_multi_floor else 0.0,
            entrance_side=entrance_side,
        )  # positions in [0, 1]
        if is_multi_floor:
            packed.insert(0, {
                "name": "staircase",
                "floor": floor_num,
                "x_norm": 0.0,
                "y_norm": 0.0,
                "width_norm": stair_w,
                "height_norm": stair_h,
                "area_sqm": _MIN_ROOM_SQM["staircase"],
                "adjacencies": [],
                "window_orientation": None,
            })
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
