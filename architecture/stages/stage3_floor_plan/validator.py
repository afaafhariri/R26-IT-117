"""
validator.py — Geometric and programmatic floor plan validator.

Checks:
  1. Room polygons do not overlap each other.
  2. All room polygons lie entirely within the buildable zone.
  3. Minimum room dimensions are met (NBC residential minimums).
  4. Every room has at least one window (exterior access to light/air).
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

# NBC minimum room areas (m²) for Sri Lankan residential construction
_MIN_ROOM_AREAS: dict[str, float] = {
    "bedroom":        9.0,
    "master bedroom": 12.0,
    "living room":    14.0,
    "dining room":    9.0,
    "kitchen":        5.5,
    "bathroom":       2.5,
    "toilet":         1.5,
    "store":          2.0,
}
_DEFAULT_MIN_AREA = 4.0


class LayoutValidator:
    """Validates a generated floor plan against geometric and NBC rules."""

    def validate(
        self, floor_plan: dict, buildable_zone: dict
    ) -> tuple[bool, list[str]]:
        """
        Run all validation checks on the floor plan.

        Args:
            floor_plan:    Floor plan dict with a 'rooms' key (list of room dicts).
            buildable_zone: Stage 2 output containing 'buildable_polygon'.

        Returns:
            (is_valid: bool, violations: list[str])
            is_valid is True only if the violations list is empty.
        """
        violations: list[str] = []

        rooms = floor_plan.get("rooms", [])
        if not rooms:
            violations.append("Floor plan contains no rooms.")
            return False, violations

        try:
            from shapely.geometry import Polygon  # type: ignore

            buildable_poly = Polygon(buildable_zone.get("buildable_polygon", []))
            room_shapes = self._build_room_shapes(rooms, Polygon)

            violations += self._check_room_containment(rooms, room_shapes, buildable_poly)
            violations += self._check_no_overlap(rooms, room_shapes)
            violations += self._check_min_dimensions(rooms)
            violations += self._check_window_access(rooms)

        except ImportError:
            logger.warning("Shapely unavailable — skipping geometric checks.")
            violations += self._check_min_dimensions(rooms)
            violations += self._check_window_access(rooms)

        except Exception as exc:
            logger.exception("Validation error")
            violations.append(f"Validation runtime error: {exc}")

        return len(violations) == 0, violations

    # ── Check implementations ─────────────────────────────────────────────

    @staticmethod
    def _build_room_shapes(rooms: list[dict], Polygon: Any) -> list[Any]:
        """Convert room polygon dicts to Shapely Polygon objects."""
        shapes = []
        for room in rooms:
            poly_coords = room.get("polygon", [])
            try:
                shapes.append(Polygon(poly_coords) if len(poly_coords) >= 3 else None)
            except Exception:
                shapes.append(None)
        return shapes

    @staticmethod
    def _check_room_containment(
        rooms: list[dict],
        room_shapes: list[Any],
        buildable: Any,
    ) -> list[str]:
        """Check that every room polygon is inside the buildable zone."""
        issues = []
        for room, shape in zip(rooms, room_shapes):
            if shape is None:
                issues.append(f"Room '{room['name']}': invalid polygon (<3 vertices).")
                continue
            if not buildable.contains(shape):
                issues.append(
                    f"Room '{room['name']}' extends outside the buildable zone."
                )
        return issues

    @staticmethod
    def _check_no_overlap(
        rooms: list[dict], room_shapes: list[Any]
    ) -> list[str]:
        """Check that no two room polygons overlap."""
        issues = []
        n = len(rooms)
        for i in range(n):
            for j in range(i + 1, n):
                a, b = room_shapes[i], room_shapes[j]
                if a is None or b is None:
                    continue
                if a.intersects(b) and not a.touches(b):
                    overlap = a.intersection(b).area
                    if overlap > 0.01:   # ignore floating-point hairline overlaps
                        issues.append(
                            f"Rooms '{rooms[i]['name']}' and '{rooms[j]['name']}' "
                            f"overlap by {overlap:.2f} m²."
                        )
        return issues

    @staticmethod
    def _check_min_dimensions(rooms: list[dict]) -> list[str]:
        """Check each room meets the NBC minimum area."""
        issues = []
        for room in rooms:
            name_lower = room.get("name", "").lower()
            area = room.get("area_sqm", 0.0)
            min_area = next(
                (v for k, v in _MIN_ROOM_AREAS.items() if k in name_lower),
                _DEFAULT_MIN_AREA,
            )
            if area < min_area:
                issues.append(
                    f"Room '{room['name']}': area {area:.1f} m² is below "
                    f"NBC minimum {min_area:.1f} m²."
                )
        return issues

    @staticmethod
    def _check_window_access(rooms: list[dict]) -> list[str]:
        """Verify every habitable room has window access."""
        # Rooms that do not require natural light/ventilation under NBC
        non_habitable = {"store", "utility", "toilet", "bathroom", "wc", "pantry"}
        issues = []
        for room in rooms:
            name_lower = room.get("name", "").lower()
            if any(t in name_lower for t in non_habitable):
                continue
            if not room.get("has_window", False):
                issues.append(
                    f"Habitable room '{room['name']}' has no window — "
                    "NBC requires natural light and ventilation."
                )
        return issues
