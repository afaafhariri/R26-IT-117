"""Rate Engine — applies ICTAD rates, district multipliers, and price escalation
to a BOQ to produce a priced trade breakdown in LKR.
"""

import logging
from datetime import date
from typing import Optional, Union

from .ictad_loader import ICTADLoader
from .district_multiplier import DistrictMultiplier
from .price_escalation import PriceEscalationModel

logger = logging.getLogger(__name__)


class RateEngine:
    """Orchestrates Layer 2: price a BOQ dict and return a trade-level cost breakdown."""

    def __init__(
        self,
        ictad_loader: Optional[ICTADLoader] = None,
        district_multiplier: Optional[DistrictMultiplier] = None,
        escalation_model: Optional[PriceEscalationModel] = None,
    ) -> None:
        self._loader = ictad_loader or ICTADLoader()
        self._district = district_multiplier or DistrictMultiplier()
        self._escalation = escalation_model or PriceEscalationModel()

    def price_boq(
        self,
        boq: dict,
        district: str,
        base_date: Union[str, date] = "2024-10-01",
        target_date: Optional[Union[str, date]] = None,
    ) -> dict:
        """Apply unit rates to BOQ quantities and return priced line items.

        Args:
            boq: Consolidated BOQ dict from BOQEngine.run() (contains 'structural',
                 'finishing', 'services', 'summary' keys).
            district: Target construction district for multiplier lookup.
            base_date: Date the ICTAD rates are valid from (ISO string or date).
            target_date: Projection date for escalation; defaults to today.

        Returns:
            Dict with 'trade_breakdown' (per-item costs), 'district_multiplier',
            'escalation_factor', 'direct_cost_lkr', and raw 'rates_used'.
        """
        if target_date is None:
            target_date = date.today()

        rates = self._loader.load_all()
        multiplier = self._district.get_multiplier(district)
        esc_factor = self._escalation.escalation_factor(base_date, target_date)

        trade_breakdown: dict[str, dict] = {}
        direct_cost_lkr = 0.0

        # Flatten all BOQ sections into a single quantity map
        quantities: dict[str, float] = {}
        for section in ("structural", "finishing", "services"):
            section_data = boq.get(section, {})
            for key, qty in section_data.items():
                if isinstance(qty, (int, float)):
                    quantities[key] = float(qty)

        for item_key, quantity in quantities.items():
            rate_entry = rates.get(item_key)
            if rate_entry is None:
                continue

            base_rate = float(rate_entry.get("rate_lkr", 0.0))
            adjusted_rate = base_rate * multiplier * esc_factor
            line_cost = adjusted_rate * quantity

            trade_breakdown[item_key] = {
                "quantity": quantity,
                "unit": rate_entry.get("unit", ""),
                "base_rate_lkr": round(base_rate, 2),
                "adjusted_rate_lkr": round(adjusted_rate, 2),
                "line_cost_lkr": round(line_cost, 2),
                "description": rate_entry.get("description", ""),
            }
            direct_cost_lkr += line_cost

        logger.info(
            "RateEngine: district=%s multiplier=%.3f esc=%.4f direct_cost=%.0f LKR",
            district, multiplier, esc_factor, direct_cost_lkr,
        )

        return {
            "trade_breakdown": trade_breakdown,
            "district": district,
            "district_multiplier": multiplier,
            "escalation_factor": round(esc_factor, 4),
            "base_date": str(base_date),
            "target_date": str(target_date),
            "direct_cost_lkr": round(direct_cost_lkr, 2),
            "rates_used": {k: v.get("rate_lkr", 0.0) for k, v in rates.items()},
        }

    def get_district_rates(self, district: str) -> dict:
        """Return ICTAD rates with district adjustment applied — for the API endpoint."""
        multiplier = self._district.get_multiplier(district)
        raw_rates = self._loader.get_rates_for_district_view(district)
        for item in raw_rates:
            item["district_adjusted_rate_lkr"] = round(
                item["base_rate_lkr"] * multiplier, 2
            )
        return {
            "district": district,
            "multiplier": multiplier,
            "rates": raw_rates,
        }
