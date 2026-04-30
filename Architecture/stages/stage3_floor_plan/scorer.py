"""Multi-dimensional quality scorer for validated floor plan layouts."""

from utils.logger import get_logger

_logger = get_logger("scorer")

_HABITABLE_TYPES = {"bedroom", "master_bedroom", "living_room", "dining"}

_IDEAL_ADJACENCIES: dict[str, list[str]] = {
    "living_room":    ["dining", "kitchen", "entrance"],
    "kitchen":        ["dining", "pantry"],
    "master_bedroom": ["bathroom", "wardrobe"],
    "bedroom":        ["bathroom"],
    "dining":         ["kitchen", "living_room"],
}


def _room_type(name: str) -> str:
    n = name.lower().replace(" ", "_")
    for key in _IDEAL_ADJACENCIES:
        if n.startswith(key):
            return key
    for h in _HABITABLE_TYPES:
        if n.startswith(h):
            return h
    return n


class LayoutScorer:
    """Scores a validated floor plan across 4 quality dimensions.

    Each score ranges from 0.0 (worst) to 1.0 (best).
    """

    def score(self, floor_plan: dict) -> dict:
        """Computes quality scores for a floor plan.

        Args:
            floor_plan: Validated floor plan dict with a rooms list.

        Returns:
            dict: {
                space_utilisation: float,
                natural_light: float,
                adjacency_quality: float,
                ventilation_potential: float,
                overall: float
            }
        """
        rooms: list[dict] = floor_plan.get("rooms", [])

        # --- Space utilisation ---
        total_room_area = sum(r.get("area_sqm", 0) for r in rooms)
        zone_area = floor_plan.get("max_footprint_sqm") or floor_plan.get(
            "total_area_sqm", total_room_area
        )
        space_utilisation = (
            min(total_room_area / zone_area, 1.0) if zone_area and zone_area > 0 else 0.0
        )

        # --- Natural light ---
        habitable = [r for r in rooms if any(
            r.get("name", "").lower().replace(" ", "_").startswith(h)
            for h in _HABITABLE_TYPES
        )]
        if habitable:
            lit = sum(1 for r in habitable if r.get("window_orientation"))
            natural_light = lit / len(habitable)
        else:
            natural_light = 0.0

        # --- Adjacency quality ---
        adj_map: dict[str, set[str]] = {}
        for room in rooms:
            rtype = _room_type(room.get("name", ""))
            adj_map[rtype] = {
                _room_type(a) for a in room.get("adjacencies", [])
            }

        total_ideal = 0
        matched = 0
        for rtype, ideal_adjs in _IDEAL_ADJACENCIES.items():
            for adj in ideal_adjs:
                total_ideal += 1
                actual = adj_map.get(rtype, set())
                if adj in actual:
                    matched += 1

        adjacency_quality = matched / total_ideal if total_ideal > 0 else 0.0

        # --- Ventilation potential ---
        orientations = {r.get("window_orientation") for r in rooms if r.get("window_orientation")}
        north_present = "north" in orientations
        south_present = "south" in orientations
        ventilation_potential = 1.0 if (north_present and south_present) else 0.5
        if "east" in orientations and "west" in orientations:
            ventilation_potential = min(ventilation_potential + 0.2, 1.0)

        # --- Overall (weighted) ---
        overall = (
            space_utilisation * 0.30
            + natural_light * 0.30
            + adjacency_quality * 0.20
            + ventilation_potential * 0.20
        )

        result = {
            "space_utilisation":   round(space_utilisation, 2),
            "natural_light":       round(natural_light, 2),
            "adjacency_quality":   round(adjacency_quality, 2),
            "ventilation_potential": round(ventilation_potential, 2),
            "overall":             round(overall, 2),
        }

        _logger.info(
            "Layout scored: overall=%.2f (utilisation=%.2f, light=%.2f, "
            "adjacency=%.2f, ventilation=%.2f)",
            overall,
            space_utilisation,
            natural_light,
            adjacency_quality,
            ventilation_potential,
        )
        return result
