"""
scorer.py — Multi-criteria quality scorer for generated floor plans.

Scores four dimensions, each in [0.0, 1.0]:
  space_utilisation    — ratio of room area to total buildable area
  natural_light        — fraction of habitable rooms with windows
  adjacency_quality    — how well room adjacencies match Sri Lankan spatial norms
  ventilation_potential — proportion of rooms on opposing sides (cross-ventilation)
"""

import logging

logger = logging.getLogger(__name__)

# Preferred adjacencies based on Sri Lankan domestic spatial conventions
_PREFERRED_ADJACENCIES: dict[str, list[str]] = {
    "living room":    ["dining room", "veranda", "entrance"],
    "dining room":    ["kitchen", "living room"],
    "kitchen":        ["dining room", "laundry", "store"],
    "master bedroom": ["bathroom", "dressing room"],
    "bedroom":        ["bathroom", "corridor"],
    "bathroom":       ["bedroom", "master bedroom"],
}

# Rooms that should have windows for full score
_HABITABLE_ROOMS = {
    "living room", "dining room", "bedroom", "master bedroom",
    "study", "home office",
}


class LayoutScorer:
    """Produces a multi-dimensional quality score for a floor plan layout."""

    def score(self, floor_plan: dict) -> dict[str, float]:
        """
        Compute quality scores for the given floor plan.

        Args:
            floor_plan: Floor plan dict with 'rooms' list and optional metadata.

        Returns:
            {
                "space_utilisation":    float,   # 0.0–1.0
                "natural_light":        float,   # 0.0–1.0
                "adjacency_quality":    float,   # 0.0–1.0
                "ventilation_potential": float,  # 0.0–1.0
                "overall":              float,   # weighted average
            }
        """
        rooms = floor_plan.get("rooms", [])
        if not rooms:
            return {
                "space_utilisation": 0.0,
                "natural_light": 0.0,
                "adjacency_quality": 0.0,
                "ventilation_potential": 0.0,
                "overall": 0.0,
            }

        try:
            s_util = self._score_space_utilisation(rooms)
            s_light = self._score_natural_light(rooms)
            s_adj = self._score_adjacency_quality(rooms)
            s_vent = self._score_ventilation(rooms)

            # Weights reflect relative importance for Sri Lankan tropical residential design
            overall = (
                0.25 * s_util
                + 0.30 * s_light
                + 0.25 * s_adj
                + 0.20 * s_vent
            )

            return {
                "space_utilisation": round(s_util, 3),
                "natural_light": round(s_light, 3),
                "adjacency_quality": round(s_adj, 3),
                "ventilation_potential": round(s_vent, 3),
                "overall": round(overall, 3),
            }

        except Exception as exc:
            logger.exception("Scoring failed: %s", exc)
            return {
                "space_utilisation": 0.0,
                "natural_light": 0.0,
                "adjacency_quality": 0.0,
                "ventilation_potential": 0.0,
                "overall": 0.0,
            }

    @staticmethod
    def _score_space_utilisation(rooms: list[dict]) -> float:
        """
        Ratio of total room area to a target of 85 % coverage.
        TODO: divide by actual buildable area once it is passed into scorer.
        """
        total_area = sum(r.get("area_sqm", 0.0) for r in rooms)
        target = 100.0  # placeholder target area in m²
        return min(total_area / target, 1.0)

    @staticmethod
    def _score_natural_light(rooms: list[dict]) -> float:
        """Fraction of habitable rooms that have a window."""
        habitable = [
            r for r in rooms
            if any(h in r.get("name", "").lower() for h in _HABITABLE_ROOMS)
        ]
        if not habitable:
            return 1.0  # no habitable rooms to penalise
        with_window = sum(1 for r in habitable if r.get("has_window", False))
        return with_window / len(habitable)

    @staticmethod
    def _score_adjacency_quality(rooms: list[dict]) -> float:
        """
        Measure how many preferred room-to-room adjacencies are satisfied.
        TODO: encode more nuanced Sri Lankan spatial norms (e.g., kitchen/utility
        away from front entrance, prayer room adjacency preferences).
        """
        room_names = {r.get("name", "").lower() for r in rooms}
        scored_pairs = 0
        satisfied_pairs = 0

        room_adj_map: dict[str, list[str]] = {
            r.get("name", "").lower(): [n.lower() for n in r.get("adjacencies", [])]
            for r in rooms
        }

        for room_name, preferred_neighbours in _PREFERRED_ADJACENCIES.items():
            if room_name not in room_names:
                continue
            actual_adj = room_adj_map.get(room_name, [])
            for neighbour in preferred_neighbours:
                if neighbour in room_names:
                    scored_pairs += 1
                    if neighbour in actual_adj:
                        satisfied_pairs += 1

        return satisfied_pairs / scored_pairs if scored_pairs else 0.5

    @staticmethod
    def _score_ventilation(rooms: list[dict]) -> float:
        """
        Estimate cross-ventilation potential.
        Heuristic: score is higher when windowed rooms are spread across
        different polygon Y positions (opposing facades).
        TODO: compute from room centroid positions relative to building bbox.
        """
        windowed = [r for r in rooms if r.get("has_window", False)]
        if len(windowed) < 2:
            return 0.3

        # Use Y midpoint of each room's polygon as a proxy for facade side
        def y_mid(room: dict) -> float:
            poly = room.get("polygon", [[0, 0]])
            return sum(pt[1] for pt in poly) / max(len(poly), 1)

        ys = [y_mid(r) for r in windowed]
        spread = max(ys) - min(ys) if ys else 0.0
        # Normalise by a representative building depth of 12 m
        return min(spread / 12.0, 1.0)
