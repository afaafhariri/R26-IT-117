"""National Building Code (NBC) Sri Lanka constraint engine."""

from utils.logger import get_logger

_logger = get_logger("nbc_constraints")


class NBCConstraintEngine:
    """Encodes NBC Sri Lanka setback and coverage requirements for residential
    construction. Values based on UDA regulations and common Local Authority
    requirements.
    """

    SETBACKS: dict[str, dict[str, float]] = {
        "national_road": {"front": 4.5, "rear": 1.5, "side": 1.0},
        "provincial":    {"front": 3.0, "rear": 1.5, "side": 1.0},
        "local":         {"front": 1.5, "rear": 1.5, "side": 1.0},
        "lane":          {"front": 1.0, "rear": 1.5, "side": 0.5},
    }

    COASTAL_DISTRICTS: set[str] = {
        "Ampara", "Trincomalee", "Batticaloa", "Jaffna", "Kilinochchi",
        "Mannar", "Galle", "Matara", "Hambantota", "Puttalam",
        "Colombo", "Gampaha", "Kalutara",
    }

    def get_setbacks(self, road_type: str) -> dict[str, float]:
        """Returns front, rear, and side setback distances in metres.

        Args:
            road_type: One of national_road | provincial | local | lane.

        Returns:
            dict: {front: float, rear: float, side: float}
        """
        if road_type not in self.SETBACKS:
            _logger.warning(
                "Unknown road_type '%s' — falling back to 'local' setbacks", road_type
            )
            return self.SETBACKS["local"]
        return self.SETBACKS[road_type]

    def get_coverage_ratio(self, district: str, is_coastal: bool) -> float:
        """Returns maximum plot coverage ratio (BCR) for the district.

        Args:
            district: District name string.
            is_coastal: Whether the plot is in a coastal district.

        Returns:
            float: Building Coverage Ratio (0.0–1.0).
        """
        if is_coastal:
            return 0.40
        if district in ("Colombo", "Gampaha"):
            return 0.65
        return 0.50

    def get_max_floors(self, plot_area_sqm: float, district: str) -> int:
        """Returns recommended maximum floors based on plot area and district rules.

        Args:
            plot_area_sqm: Total plot area in square metres.
            district: District name string.

        Returns:
            int: Maximum recommended number of floors.
        """
        if plot_area_sqm < 200:
            return 1
        if plot_area_sqm <= 500:
            return 2
        return 3
