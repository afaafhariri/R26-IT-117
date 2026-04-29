"""Services Bill of Quantities — electrical wiring points and plumbing fixtures."""

import logging

logger = logging.getLogger(__name__)

# Electrical wiring points per room type
_ELECTRICAL_POINTS: dict[str, int] = {
    "living_room": 8,
    "master_bedroom": 6,
    "bedroom": 4,
    "kitchen": 8,
    "bathroom": 3,
    "dining_room": 4,
    "study": 4,
    "garage": 3,
    "store": 2,
    "balcony": 2,
}

# Plumbing fixtures per bathroom (cold + hot supply, drainage)
_FIXTURES_PER_BATHROOM = {
    "wc_pan": 1,
    "washbasin": 1,
    "shower_or_bathtub": 1,
    "floor_trap": 1,
}


class ServicesBOQ:
    """Estimates electrical and plumbing services quantities from room data."""

    def calculate(self, rooms: dict) -> dict:
        """Return services BOQ for electrical wiring points and plumbing fixtures.

        Args:
            rooms: Dict mapping room type strings to counts, e.g.
                   {"living_room": 1, "bedroom": 3, "bathroom": 2}.

        Returns:
            Dict with electrical_points (int), plumbing_fixtures (dict),
            total_plumbing_fixtures (int), and a per-room breakdown.
        """
        if not rooms:
            logger.warning("Empty rooms dict supplied to ServicesBOQ — returning zeros.")
            return {
                "electrical_points": 0,
                "plumbing_fixtures": {},
                "total_plumbing_fixtures": 0,
                "electrical_breakdown": {},
            }

        electrical_breakdown: dict[str, int] = {}
        total_electrical = 0

        for room_type, count in rooms.items():
            normalized = room_type.lower().replace(" ", "_")
            points_per_room = _ELECTRICAL_POINTS.get(normalized, 4)  # default 4
            subtotal = points_per_room * int(count)
            electrical_breakdown[room_type] = subtotal
            total_electrical += subtotal

        # Consumer unit, distribution board, and earth continuity — fixed addition
        total_electrical += 6

        bathroom_count: int = int(rooms.get("bathroom", 0))
        plumbing_fixtures: dict[str, int] = {
            fixture: qty * bathroom_count
            for fixture, qty in _FIXTURES_PER_BATHROOM.items()
        }
        # Kitchen sink is separate
        kitchen_count: int = int(rooms.get("kitchen", 0))
        plumbing_fixtures["kitchen_sink"] = kitchen_count
        plumbing_fixtures["kitchen_waste_trap"] = kitchen_count
        # Outdoor hose bibs
        plumbing_fixtures["hose_bib"] = 2

        total_plumbing = sum(plumbing_fixtures.values())

        result = {
            "electrical_points": total_electrical,
            "electrical_breakdown": electrical_breakdown,
            "plumbing_fixtures": plumbing_fixtures,
            "total_plumbing_fixtures": total_plumbing,
        }
        logger.debug("Services BOQ: %s", result)
        return result
