"""Rate Engine — applies ICTAD rates, district multipliers, and price escalation
to a BOQ to produce a priced trade breakdown in LKR.
"""

import logging
from datetime import date
from typing import Optional, Union

from .ictad_loader import ICTADLoader
from .district_multiplier import DistrictMultiplier
from .price_escalation import PriceEscalationModel
from .material_catalog import MaterialCatalog

logger = logging.getLogger(__name__)


class RateEngine:
    """Orchestrates Layer 2: price a BOQ dict and return a trade-level cost breakdown."""

    def __init__(
        self,
        ictad_loader: Optional[ICTADLoader] = None,
        district_multiplier: Optional[DistrictMultiplier] = None,
        escalation_model: Optional[PriceEscalationModel] = None,
        material_catalog: Optional[MaterialCatalog] = None,
    ) -> None:
        self._loader = ictad_loader or ICTADLoader()
        self._district = district_multiplier or DistrictMultiplier()
        self._escalation = escalation_model or PriceEscalationModel()
        self._catalog = material_catalog or MaterialCatalog()

    def price_boq(
        self,
        boq: dict,
        district: str,
        base_date: Union[str, date] = "2024-10-01",
        target_date: Optional[Union[str, date]] = None,
        material_selections: Optional[dict[str, str]] = None,
    ) -> dict:
        """Apply unit rates to BOQ quantities and return priced line items.

        Args:
            boq: Consolidated BOQ dict from BOQEngine.run() (contains 'structural',
                 'finishing', 'services', 'summary' keys).
            district: Target construction district for multiplier lookup.
            base_date: Date the ICTAD rates are valid from (ISO string or date).
            target_date: Projection date for escalation; defaults to today.
            material_selections: Optional map of BOQ part key -> material variant
                 key (e.g. {'door_count': 'plywood_flush'}). Selected parts are
                 priced from the material catalog instead of the ICTAD schedule;
                 unselected parts keep the ICTAD rate unchanged.

        Returns:
            Dict with 'trade_breakdown' (per-item costs), 'district_multiplier',
            'escalation_factor', 'direct_cost_lkr', raw 'rates_used', plus
            'material_selections' applied and per-part 'material_alternatives'.
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

        selections = material_selections or {}
        selections_applied: dict[str, str] = {}

        for item_key, quantity in quantities.items():
            rate_entry = rates.get(item_key)

            # Material variant override: catalog rate replaces the ICTAD rate
            material_entry = None
            selected_material = selections.get(item_key)
            if selected_material:
                material_entry = self._catalog.get(item_key, selected_material)
                if material_entry is None:
                    logger.warning(
                        "Unknown material '%s' for part '%s' — using ICTAD rate.",
                        selected_material, item_key,
                    )

            if material_entry is None and rate_entry is None:
                continue

            if material_entry is not None:
                base_rate = material_entry["rate_lkr"]
                unit = material_entry["unit"]
                description = material_entry["description"]
                selections_applied[item_key] = selected_material
            else:
                base_rate = float(rate_entry.get("rate_lkr", 0.0))
                unit = rate_entry.get("unit", "")
                description = rate_entry.get("description", "")

            adjusted_rate = base_rate * multiplier * esc_factor
            line_cost = adjusted_rate * quantity

            trade_breakdown[item_key] = {
                "quantity": quantity,
                "unit": unit,
                "base_rate_lkr": round(base_rate, 2),
                "adjusted_rate_lkr": round(adjusted_rate, 2),
                "line_cost_lkr": round(line_cost, 2),
                "description": description,
            }
            if material_entry is not None:
                trade_breakdown[item_key]["material"] = selected_material
                trade_breakdown[item_key]["rate_source"] = material_entry["rate_source"]
            direct_cost_lkr += line_cost

        material_alternatives = self._build_alternatives(
            quantities, selections_applied, multiplier, esc_factor
        )

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
            "material_selections": selections_applied,
            "material_alternatives": material_alternatives,
        }

    def _build_alternatives(
        self,
        quantities: dict[str, float],
        selections_applied: dict[str, str],
        multiplier: float,
        esc_factor: float,
    ) -> dict[str, list[dict]]:
        """Per-part cost comparison across all material variants present in the BOQ."""
        alternatives: dict[str, list[dict]] = {}
        for part_key in self._catalog.parts():
            quantity = quantities.get(part_key, 0.0)
            if quantity <= 0:
                continue
            rows = []
            for variant in self._catalog.variants(part_key):
                adjusted_rate = variant["rate_lkr"] * multiplier * esc_factor
                rows.append({
                    "material": variant["material_key"],
                    "description": variant["description"],
                    "unit": variant["unit"],
                    "unit_rate_lkr": round(adjusted_rate, 2),
                    "line_cost_lkr": round(adjusted_rate * quantity, 2),
                    "rate_source": variant["rate_source"],
                    "is_selected": variant["material_key"] == selections_applied.get(part_key),
                })
            if rows:
                alternatives[part_key] = rows
        return alternatives

    def get_material_catalog_view(self) -> dict:
        """Catalog listing for the GET /materials endpoint."""
        return {
            part_key: [
                {
                    "material": v["material_key"],
                    "description": v["description"],
                    "unit": v["unit"],
                    "rate_lkr": v["rate_lkr"],
                    "rate_source": v["rate_source"],
                    "last_updated": v["last_updated"],
                }
                for v in self._catalog.variants(part_key)
            ]
            for part_key in self._catalog.parts()
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
