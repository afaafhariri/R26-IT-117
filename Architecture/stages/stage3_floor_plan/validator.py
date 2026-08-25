"""Geometric and programmatic floor plan validator."""

from shapely.geometry import box, Polygon

from utils.logger import get_logger

_logger = get_logger("validator")

_HABITABLE_TYPES = {"bedroom", "master_bedroom", "living_room", "dining"}

_MIN_ROOM_DIMS: dict[str, dict[str, float]] = {
    "bedroom":        {"min_area": 9.0,  "min_width": 2.7},
    "master_bedroom": {"min_area": 12.0, "min_width": 3.0},
    "living_room":    {"min_area": 16.0, "min_width": 3.5},
    "kitchen":        {"min_area": 6.0,  "min_width": 2.0},
    "bathroom":       {"min_area": 3.5,  "min_width": 1.5},
    "dining":         {"min_area": 10.0, "min_width": 2.7},
    "garage":         {"min_area": 14.0, "min_width": 2.8},
}


def _room_key(name: str) -> str:
    """Normalises a room name to a MIN_ROOM_DIMS lookup key."""
    name_lower = name.lower().replace(" ", "_")
    for key in _MIN_ROOM_DIMS:
        if name_lower.startswith(key):
            return key
    return ""


def _room_box(room: dict) -> box:
    return box(
        room["x_norm"],
        room["y_norm"],
        room["x_norm"] + room["width_norm"],
        room["y_norm"] + room["height_norm"],
    )


class LayoutValidator:
    """Validates a generated floor plan layout against geometric and programmatic
    constraints derived from NBC Sri Lanka and spatial logic.
    """

    def validate(
        self, floor_plan: dict, buildable_zone: dict
    ) -> tuple[bool, list[str]]:
        """Validates the floor plan against 5 constraint checks.

        Args:
            floor_plan: Dict from LLM generator with a rooms list.
            buildable_zone: Stage 2 output with max_total_built_sqm.

        Returns:
            tuple: (is_valid: bool, violations: list[str])
                violations is an empty list when is_valid is True.
        """
        rooms: list[dict] = floor_plan.get("rooms", [])
        violations: list[str] = []

        # Check 1 — total area within budget (5% tolerance)
        max_built = buildable_zone.get("max_total_built_sqm", float("inf"))
        total = sum(r.get("area_sqm", 0) for r in rooms)
        if total > max_built * 1.05:
            violations.append(
                f"Total area {total:.1f} sqm exceeds maximum {max_built:.1f} sqm "
                f"(5% tolerance)"
            )

        # Check 2 — minimum room dimensions
        for room in rooms:
            key = _room_key(room.get("name", ""))
            if not key:
                continue
            limits = _MIN_ROOM_DIMS[key]
            area = room.get("area_sqm", 0)
            if area < limits["min_area"]:
                violations.append(
                    f"Room '{room['name']}' area {area:.1f} sqm is below "
                    f"minimum {limits['min_area']} sqm"
                )

        # Check 3 — room non-overlap (> 5% of smaller room area = violation)
        # Only compare rooms on the same floor — different floors share the same
        # normalised coordinate space but are physically independent.
        boxes = [_room_box(r) for r in rooms]
        from collections import defaultdict as _dd
        by_floor: dict = _dd(list)
        for idx, room in enumerate(rooms):
            by_floor[room.get("floor", 1)].append(idx)

        for floor_indices in by_floor.values():
            for ii, i in enumerate(floor_indices):
                for j in floor_indices[ii + 1:]:
                    bi, bj = _room_box(rooms[i]), _room_box(rooms[j])
                    inter = bi.intersection(bj)
                    if not inter.is_empty:
                        smaller_area = min(bi.area, bj.area)
                        if smaller_area > 0 and inter.area / smaller_area > 0.05:
                            violations.append(
                                f"Rooms '{rooms[i]['name']}' and '{rooms[j]['name']}' "
                                f"overlap by {inter.area / smaller_area:.0%}"
                            )

        # Check 4 — all rooms within buildable zone
        buildable_coords = buildable_zone.get("buildable_polygon", [])
        if len(buildable_coords) >= 3:
            zone_poly = Polygon(buildable_coords)
            for room, rb in zip(rooms, boxes):
                if not zone_poly.is_valid:
                    break
                if rb.area > 0 and zone_poly.intersection(rb).area / rb.area < 0.95:
                    violations.append(
                        f"Room '{room['name']}' is less than 95% within the buildable zone"
                    )

        # Check 5 — window access for habitable rooms
        for room in rooms:
            rname = room.get("name", "").lower().replace(" ", "_")
            is_habitable = any(rname.startswith(h) for h in _HABITABLE_TYPES)
            if is_habitable and not room.get("window_orientation"):
                violations.append(
                    f"Habitable room '{room['name']}' has no window_orientation set"
                )

        is_valid = len(violations) == 0
        if violations:
            _logger.warning(
                "Layout validation failed: %d violations", len(violations)
            )
        else:
            _logger.info("Layout validation passed")

        return is_valid, violations
