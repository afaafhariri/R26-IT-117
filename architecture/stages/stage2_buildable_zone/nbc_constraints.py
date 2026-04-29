"""
nbc_constraints.py — Sri Lanka National Building Code constraint engine.

Provides setback distances and maximum plot coverage ratios as defined
in the NBC and local authority by-laws.

Reference: UDA (Urban Development Authority) Development Control Regulations,
           NBC Part 7 — Sri Lanka.
"""

import logging

logger = logging.getLogger(__name__)

# ── Setback tables (metres) ───────────────────────────────────────────────
# Source: UDA DCR Table — residential zone defaults.
# TODO: extend with zone-specific overrides (coastal, heritage, flood zones).

_SETBACKS: dict[str, dict[str, float]] = {
    "national_road": {"front": 4.5, "rear": 1.5, "side": 1.0},
    "provincial":    {"front": 3.0, "rear": 1.5, "side": 1.0},
    "local":         {"front": 2.0, "rear": 1.5, "side": 0.9},
    "lane":          {"front": 1.5, "rear": 1.2, "side": 0.6},
}

_DEFAULT_SETBACK = {"front": 2.0, "rear": 1.5, "side": 0.9}

# ── District coverage ratios ──────────────────────────────────────────────
# Higher-density districts allow slightly higher coverage.
# TODO: load from PostGIS district layer for precise values.

_DISTRICT_COVERAGE: dict[str, float] = {
    "colombo":      0.60,
    "gampaha":      0.55,
    "kandy":        0.50,
    "galle":        0.50,
    "kalutara":     0.50,
    "matara":       0.50,
    "hambantota":   0.45,
    "kurunegala":   0.50,
    "ratnapura":    0.45,
    "badulla":      0.45,
    "nuwara eliya": 0.40,
    "trincomalee":  0.45,
    "batticaloa":   0.45,
    "ampara":       0.45,
    "jaffna":       0.50,
    "vavuniya":     0.45,
}

_DEFAULT_COVERAGE = 0.50


class NBCConstraintEngine:
    """
    Returns NBC-compliant setbacks and coverage ratios for a given road type
    and district, used to derive the buildable zone footprint.
    """

    def get_setbacks(self, road_type: str) -> dict[str, float]:
        """
        Return front, rear, and side setback distances in metres.

        Args:
            road_type: One of 'national_road', 'provincial', 'local', 'lane'.

        Returns:
            {"front": float, "rear": float, "side": float}

        Notes:
            Falls back to 'local' defaults for unrecognised road_type values.
        """
        normalised = road_type.lower().strip()
        if normalised not in _SETBACKS:
            logger.warning(
                "Unknown road_type '%s' — using local road defaults.", road_type
            )
            return dict(_DEFAULT_SETBACK)

        return dict(_SETBACKS[normalised])

    def get_coverage_ratio(self, district: str) -> float:
        """
        Return the maximum permitted plot coverage ratio (0.0 – 1.0).

        Args:
            district: District name (case-insensitive), e.g. 'Colombo'.

        Returns:
            Float between 0.0 and 1.0 representing max footprint / plot area.

        Notes:
            Defaults to 0.50 for districts not in the lookup table.
        """
        normalised = district.lower().strip()
        ratio = _DISTRICT_COVERAGE.get(normalised, _DEFAULT_COVERAGE)
        logger.debug("Coverage ratio for '%s': %.2f", district, ratio)
        return ratio

    def get_floor_area_ratio(self, district: str) -> float:
        """
        Return the Floor Area Ratio (FAR) for gross floor area calculation.
        TODO: populate from UDA zoning tables.
        """
        # Placeholder: residential zones typically allow FAR 1.0–2.5
        return 1.5

    def get_max_building_height_m(self, road_type: str, district: str) -> float:
        """
        Return the maximum permitted building height in metres.
        TODO: derive from NBC Table 6 and local authority height limits.
        """
        # Placeholder: most Sri Lankan residential zones allow 10 m (≈ 3 floors)
        return 10.0
