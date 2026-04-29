"""
orientation_solver.py — Determines optimal building orientation.

Recommends the principal compass orientation for the floor plan layout
based on the plot's primary axis and solar/wind considerations for
Sri Lanka's climate zones.
"""

import logging
import math

logger = logging.getLogger(__name__)

# Sri Lanka lies between 6°N – 10°N.  Best practice: long axis East-West
# to minimise east/west solar gain and maximise cross-ventilation (SW monsoon).
_PREFERRED_SOLAR_AXIS_DEG = 90.0   # East-West long axis
_MONSOON_DIRECTION_DEG = 225.0     # South-West monsoon prevailing wind


class OrientationSolver:
    """Recommends optimal building orientation for a Sri Lankan residential plot."""

    def solve(self, plot_orientation_degrees: float) -> dict:
        """
        Derive the recommended building orientation and rotation delta.

        Args:
            plot_orientation_degrees: Primary axis angle of the plot
                                       (degrees clockwise from North).

        Returns:
            {
                "plot_orientation_deg":     float,
                "recommended_building_deg": float,  # recommended long-axis angle
                "rotation_delta_deg":       float,  # CW rotation to apply
                "solar_efficiency_score":   float,  # 0.0–1.0
                "ventilation_score":        float,  # 0.0–1.0
                "rationale":               str,
            }
        """
        try:
            plot_norm = plot_orientation_degrees % 360.0
            recommended = self._compute_recommended(plot_norm)
            delta = self._angular_delta(plot_norm, recommended)
            solar = self._solar_score(recommended)
            ventilation = self._ventilation_score(recommended)

            return {
                "plot_orientation_deg": round(plot_norm, 2),
                "recommended_building_deg": round(recommended, 2),
                "rotation_delta_deg": round(delta, 2),
                "solar_efficiency_score": round(solar, 3),
                "ventilation_score": round(ventilation, 3),
                "rationale": self._rationale(recommended, solar, ventilation),
            }

        except Exception as exc:
            logger.exception("Orientation solving failed")
            raise RuntimeError(f"Orientation solver error: {exc}") from exc

    def _compute_recommended(self, plot_degrees: float) -> float:
        """
        Snap the plot axis to the nearest 15° increment aligned to
        the preferred East-West solar axis.
        TODO: incorporate site-specific shading from adjacents.
        """
        # Prefer East-West (90° or 270°) orientation
        candidate_a = _PREFERRED_SOLAR_AXIS_DEG
        candidate_b = (_PREFERRED_SOLAR_AXIS_DEG + 180.0) % 360.0

        dist_a = self._angular_distance(plot_degrees, candidate_a)
        dist_b = self._angular_distance(plot_degrees, candidate_b)

        return candidate_a if dist_a <= dist_b else candidate_b

    @staticmethod
    def _angular_distance(a: float, b: float) -> float:
        """Smallest angle between two bearings (0–180)."""
        diff = abs(a - b) % 360.0
        return min(diff, 360.0 - diff)

    @staticmethod
    def _angular_delta(from_deg: float, to_deg: float) -> float:
        """Signed clockwise rotation delta from from_deg to to_deg."""
        delta = (to_deg - from_deg) % 360.0
        if delta > 180.0:
            delta -= 360.0
        return delta

    @staticmethod
    def _solar_score(building_deg: float) -> float:
        """
        Score solar efficiency based on long-axis alignment.
        Ideal is exactly 90° (East-West).  Worst is 0°/180° (North-South).
        """
        distance = OrientationSolver._angular_distance(building_deg, _PREFERRED_SOLAR_AXIS_DEG)
        return max(0.0, 1.0 - (distance / 90.0))

    @staticmethod
    def _ventilation_score(building_deg: float) -> float:
        """
        Score natural ventilation.  Best when long axis is perpendicular
        to prevailing SW monsoon (225°) so cross-ventilation is maximised.
        Perpendicular to 225° is 135° or 315°.
        """
        perpendicular = (_MONSOON_DIRECTION_DEG + 90.0) % 360.0
        distance = OrientationSolver._angular_distance(building_deg, perpendicular)
        return max(0.0, 1.0 - (distance / 90.0))

    @staticmethod
    def _rationale(deg: float, solar: float, ventilation: float) -> str:
        compass = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"][int((deg + 22.5) / 45) % 8]
        return (
            f"Recommended orientation: {compass} ({deg:.0f}°). "
            f"Solar score: {solar:.2f}, ventilation score: {ventilation:.2f}. "
            "Aligns building long axis East-West to minimise tropical solar gain "
            "and harness South-West monsoon cross-ventilation."
        )
