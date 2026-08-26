"""Report builder — assembles all pipeline outputs into the final Cost Report JSON."""

import logging
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def _labour_days_estimate(boq_summary: dict) -> int:
    """Rough estimate of total site labour days from BOQ aggregates."""
    concrete_m3 = boq_summary.get("total_concrete_m3", 0.0)
    brickwork_m3 = boq_summary.get("total_brickwork_m3", 0.0)
    floor_area = boq_summary.get("floor_area_sqm", 0.0)
    # Indicative norms: 10 days/m3 concrete, 8 days/m3 masonry, 0.5 days/m2 finishes
    return int(concrete_m3 * 10 + brickwork_m3 * 8 + floor_area * 0.5)


def _structural_complexity(structural: dict) -> float:
    """Score 0–1 based on column/slab volumes relative to total concrete."""
    cols = structural.get("rc_columns_m3", 0.0)
    slab = structural.get("rc_slab_m3", 0.0)
    total = cols + slab + structural.get("foundation_concrete_m3", 0.0) + 0.001
    return round(min(1.0, (cols + slab) / total), 3)


class ReportBuilder:
    """Assembles the final Cost Report JSON for downstream components."""

    def build(
        self,
        boq: dict,
        rates: dict,
        prediction: dict,
        risk: dict,
        contingency: dict,
        schema: dict | None = None,
    ) -> dict:
        """Produce the full Cost Report JSON.

        Args:
            boq: Output from BOQEngine.run().
            rates: Output from RateEngine.price_boq() — contains trade_breakdown
                   and direct_cost_lkr.
            prediction: Output from EnsembleCostPredictor.predict().
            risk: Output from RiskScorer.score().
            contingency: Output from ContingencyCalculator.calculate().
            schema: The input Building Schema dict. Only its location fields are
                    used, and only to forward them downstream — C02 does not
                    price by district.

        Returns:
            Full Cost Report dict ready for JSON serialisation.
        """
        estimate_id = str(uuid.uuid4())
        generated_at = datetime.now(tz=timezone.utc).isoformat()

        grand_total = contingency.get("grand_total_lkr", 0.0)
        floor_area = boq.get("summary", {}).get("floor_area_sqm", 1.0)
        cost_per_sqm = round(grand_total / max(floor_area, 1.0), 2)

        # Use ensemble ML bounds if available; fall back to contingency ±15%
        point = prediction.get("point_estimate_lkr", grand_total)
        lower = prediction.get("lower_bound_lkr") or round(grand_total * 0.85, 2)
        upper = prediction.get("upper_bound_lkr") or round(grand_total * 1.15, 2)

        boq_summary = boq.get("summary", {})
        structural = boq.get("structural", {})
        finishing = boq.get("finishing", {})
        services = boq.get("services", {})
        trade_breakdown = rates.get("trade_breakdown", {})

        # Group trade breakdown into high-level categories
        structural_keys = {
            "foundation_excavation_m3", "blinding_concrete_m3", "foundation_concrete_m3",
            "rc_columns_m3", "rc_slab_m3", "external_brickwork_m3", "internal_blockwork_m3",
            "roof_area_sqm", "steel_kg_estimate",
        }
        finishing_keys = {
            "floor_tile_sqm", "wall_plaster_sqm", "ceiling_sqm",
            "door_count", "window_count", "paint_sqm",
        }
        services_keys = {"electrical_points", "total_plumbing_fixtures"}

        def _sum_keys(keys: set) -> float:
            return sum(
                trade_breakdown.get(k, {}).get("line_cost_lkr", 0.0) for k in keys
            )

        trade_value_breakdown = {
            "structural_lkr": round(_sum_keys(structural_keys), 2),
            "finishing_lkr": round(_sum_keys(finishing_keys), 2),
            "services_lkr": round(_sum_keys(services_keys), 2),
        }

        shap_drivers = prediction.get("shap_explanations", [])

        report = {
            "estimate_id": estimate_id,
            "generated_at": generated_at,
            "summary": {
                "total_lkr": round(grand_total, 2),
                "lower_bound_lkr": round(lower, 2),
                "upper_bound_lkr": round(upper, 2),
                "cost_per_sqm_lkr": cost_per_sqm,
                "confidence_level": 0.90,
                "ml_point_estimate_lkr": round(point, 2),
                "direct_cost_lkr": rates.get("direct_cost_lkr", 0.0),
            },
            "boq_summary": {
                "structural": structural,
                "finishing": finishing,
                "services": {
                    k: v for k, v in services.items()
                    if not isinstance(v, dict)  # exclude nested breakdown dicts
                },
                "aggregates": boq_summary,
            },
            "trade_breakdown": trade_breakdown,
            "material_options": {
                "selections": rates.get("material_selections", {}),
                "alternatives": rates.get("material_alternatives", {}),
            },
            "contingency_breakdown": contingency.get("breakdown", []),
            "risk_factors_applied": risk.get("factors_applied", []),
            "shap_top_drivers": shap_drivers,
            "model_metadata": {
                "xgboost_prediction_lkr": prediction.get("xgboost_prediction", 0.0),
                "model": "xgboost",
            },
            "rate_metadata": {
                "escalation_factor": rates.get("escalation_factor", 1.0),
                "base_date": rates.get("base_date", ""),
                "target_date": rates.get("target_date", ""),
                # Forwarded straight from the C01 Building Schema. C02 has no
                # use for these itself, but C03 reads them off rate_metadata to
                # populate the planned schedule it hands to C04, which requires
                # both. Dropping them here is what previously left every
                # downstream project stamped "Unknown".
                "district": (schema or {}).get("district") or "",
                "province": (schema or {}).get("province") or "",
            },
            "feeds_downstream": {
                "total_labour_days": _labour_days_estimate(boq_summary),
                "structural_complexity_score": _structural_complexity(structural),
                "trade_value_breakdown": trade_value_breakdown,
                "floor_area_sqm": floor_area,
                "bathroom_count": boq_summary.get("bathroom_count",
                    services.get("total_plumbing_fixtures", 0) // 4),
            },
        }

        logger.info(
            "Cost Report built: id=%s total=%.0f LKR per_sqm=%.0f LKR",
            estimate_id, grand_total, cost_per_sqm,
        )
        return report
