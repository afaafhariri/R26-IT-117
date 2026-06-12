"""Risk scorer — quantifies project-specific risk factors as additive percentage premiums."""

import logging

logger = logging.getLogger(__name__)

# Remote districts (Vavuniya multiplier >= 1.18 is used as the proxy threshold)
_REMOTE_DISTRICTS = {
    "Vavuniya", "Mullaitivu", "Kilinochchi", "Mannar",
    "Monaragala", "Badulla", "Nuwara Eliya",
}

_COASTAL_DISTRICTS = {
    "Colombo", "Gampaha", "Kalutara", "Galle", "Matara",
    "Hambantota", "Puttalam", "Jaffna", "Trincomalee", "Batticaloa", "Ampara",
}


class RiskScorer:
    """Evaluates construction risk factors and returns a total risk percentage."""

    def score(
        self,
        site_schema: dict,
        building_schema: dict,
        finish_grade: str,
    ) -> dict:
        """Compute additive risk factors and total risk percentage.

        Risk factors (additive):
          - Remote district: +8%
          - Coastal site: +5%
          - Multi-storey (floors > 1): +7%
          - Constrained plot (< 200 m²): +5%
          - Luxury finish grade: +10%

        Args:
            site_schema: Site metadata dict (district, is_coastal, plot_area, terrain).
            building_schema: Building schema dict (floors, footprint_sqm, etc.).
            finish_grade: 'economy', 'mid', or 'luxury'.

        Returns:
            Dict with 'factors_applied' (list of dicts) and 'total_risk_pct' (float).
        """
        district = str(site_schema.get("district", "Colombo"))
        is_coastal = bool(
            site_schema.get("is_coastal", False)
            or district in _COASTAL_DISTRICTS
        )
        floors = int(building_schema.get("floors", 1))
        plot_area = float(
            site_schema.get("plot_area", building_schema.get("plot_area", 500.0))
        )
        grade = finish_grade.lower()

        factors_applied: list[dict] = []
        total_risk = 0.0

        def _add_factor(name: str, pct: float, reason: str) -> None:
            nonlocal total_risk
            total_risk += pct
            factors_applied.append(
                {"factor": name, "added_pct": round(pct * 100, 1), "reason": reason}
            )

        if district in _REMOTE_DISTRICTS:
            _add_factor(
                "remote_district",
                0.08,
                f"District '{district}' has limited material supply chains and labour.",
            )

        if is_coastal:
            _add_factor(
                "coastal_site",
                0.05,
                "Coastal environment increases corrosion risk and material protection costs.",
            )

        if floors > 1:
            _add_factor(
                "multi_storey",
                0.07,
                f"Building is {floors} storeys — higher structural complexity and scaffolding costs.",
            )

        if plot_area < 200.0:
            _add_factor(
                "constrained_plot",
                0.05,
                f"Plot area ({plot_area:.0f} m²) is below 200 m² — limited laydown space increases costs.",
            )

        if grade == "luxury":
            _add_factor(
                "luxury_finish",
                0.10,
                "Luxury specifications require specialist trades and imported materials.",
            )

        logger.info(
            "Risk score for district=%s coastal=%s floors=%d grade=%s: %.1f%%",
            district, is_coastal, floors, grade, total_risk * 100,
        )

        return {
            "factors_applied": factors_applied,
            "total_risk_pct": round(total_risk, 4),
            "total_risk_display": f"{total_risk * 100:.1f}%",
        }
