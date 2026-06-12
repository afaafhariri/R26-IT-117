"""District cost multipliers relative to Colombo baseline (1.00).

Multipliers reflect logistics, labour availability, and material transport costs
across Sri Lankan districts. Values are calibrated against ICTAD regional indices.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

_DISTRICT_MULTIPLIERS: dict[str, float] = {
    # Western Province
    "Colombo": 1.00,
    "Gampaha": 1.02,
    "Kalutara": 1.04,
    # Central Province
    "Kandy": 1.05,
    "Matale": 1.08,
    "Nuwara Eliya": 1.10,
    # Southern Province
    "Galle": 1.06,
    "Matara": 1.07,
    "Hambantota": 1.09,
    # Northern Province
    "Jaffna": 1.11,
    "Kilinochchi": 1.16,
    "Mannar": 1.15,
    "Vavuniya": 1.18,
    "Mullaitivu": 1.22,
    # Eastern Province
    "Ampara": 1.12,
    "Batticaloa": 1.13,
    "Trincomalee": 1.14,
    # North Western Province
    "Kurunegala": 1.03,
    "Puttalam": 1.06,
    # North Central Province
    "Anuradhapura": 1.09,
    "Polonnaruwa": 1.10,
    # Uva Province
    "Badulla": 1.11,
    "Monaragala": 1.13,
    # Sabaragamuwa Province
    "Ratnapura": 1.08,
    "Kegalle": 1.06,
}


class DistrictMultiplier:
    """Provides district-level cost adjustment multipliers."""

    def __init__(
        self, custom_multipliers: Optional[dict[str, float]] = None
    ) -> None:
        self._multipliers: dict[str, float] = dict(_DISTRICT_MULTIPLIERS)
        if custom_multipliers:
            self._multipliers.update(custom_multipliers)

    def get_multiplier(self, district: str) -> float:
        """Return the cost multiplier for a named district.

        Falls back to 1.05 (national average) if district is unknown.

        Args:
            district: Sri Lankan district name (case-sensitive as stored).

        Returns:
            Float multiplier >= 1.00.
        """
        multiplier = self._multipliers.get(district)
        if multiplier is None:
            logger.warning(
                "District '%s' not in multiplier table — using national average 1.05.",
                district,
            )
            return 1.05
        return multiplier

    def apply(self, base_rate: float, district: str) -> float:
        """Multiply a base rate by the district factor.

        Args:
            base_rate: Base unit rate in LKR before district adjustment.
            district: Target district name.

        Returns:
            District-adjusted rate in LKR.
        """
        return round(base_rate * self.get_multiplier(district), 2)

    @property
    def all_districts(self) -> list[str]:
        """Return all supported district names sorted alphabetically."""
        return sorted(self._multipliers.keys())

    def as_dict(self) -> dict[str, float]:
        """Return the full multiplier table as a plain dict."""
        return dict(self._multipliers)
