"""Contingency and on-cost calculator — builds up the grand total from direct cost.

Applied in sequence so each percentage operates on the running subtotal:
  1. Risk contingency       direct_cost × risk_pct
  2. Site establishment     3.0%
  3. Supervision            3.5%
  4. Insurance              1.0%
  5. Bonds & permits        1.5%
  6. Profit & overhead      12.0%
  7. Design contingency     5.0%
"""

import logging

logger = logging.getLogger(__name__)

_ONCOSTS: list[tuple[str, float]] = [
    ("site_establishment", 0.030),
    ("supervision", 0.035),
    ("insurance", 0.010),
    ("bonds_permits", 0.015),
    ("profit_overhead", 0.120),
    ("design_contingency", 0.050),
]


class ContingencyCalculator:
    """Applies risk contingency and standard on-costs to produce a grand total."""

    def calculate(self, direct_cost: float, risk_pct: float) -> dict:
        """Build cost breakdown from direct cost to grand total.

        Args:
            direct_cost: Sum of all priced BOQ line items in LKR.
            risk_pct: Total risk fraction from RiskScorer (e.g. 0.20 = 20%).

        Returns:
            Dict with 'breakdown' (list of dicts) and 'grand_total_lkr' (float).
        """
        if direct_cost <= 0:
            logger.warning("ContingencyCalculator received direct_cost=%.2f — check pipeline.", direct_cost)

        breakdown: list[dict] = []
        running_total = float(direct_cost)

        # Step 1: risk contingency on the direct cost
        risk_amount = direct_cost * risk_pct
        running_total += risk_amount
        breakdown.append(
            {
                "item": "risk_contingency",
                "rate_pct": round(risk_pct * 100, 2),
                "amount_lkr": round(risk_amount, 2),
                "cumulative_lkr": round(running_total, 2),
            }
        )

        # Steps 2–7: sequential on-costs applied to the running subtotal
        for label, rate in _ONCOSTS:
            amount = running_total * rate
            running_total += amount
            breakdown.append(
                {
                    "item": label,
                    "rate_pct": round(rate * 100, 1),
                    "amount_lkr": round(amount, 2),
                    "cumulative_lkr": round(running_total, 2),
                }
            )

        grand_total = round(running_total, 2)
        logger.info(
            "Contingency: direct=%.0f risk=%.1f%% grand_total=%.0f LKR",
            direct_cost, risk_pct * 100, grand_total,
        )

        return {
            "direct_cost_lkr": round(direct_cost, 2),
            "breakdown": breakdown,
            "grand_total_lkr": grand_total,
            "total_oncost_lkr": round(grand_total - direct_cost, 2),
            "oncost_pct": round((grand_total / max(direct_cost, 1) - 1) * 100, 2),
        }
