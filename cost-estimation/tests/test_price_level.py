"""Tests for main._price_factor: the model's figures follow the request's price level."""

import pytest

import main
from layers.layer1_boq.boq_engine import BOQEngine
from layers.layer4_risk_adjuster.contingency import ContingencyCalculator
from layers.layer4_risk_adjuster.risk_scorer import RiskScorer


def _factor(schema_dict, **overrides):
    schema = main.BuildingSchema(**{**schema_dict, **overrides})
    boq = BOQEngine().run(schema.to_dict())
    selections = main.default_selections(schema.finish_grade)
    selections.update(schema.materials)
    rates = main._rate_engine.price_boq(
        boq,
        base_date=schema.base_rate_date,
        target_date=schema.target_date,
        material_selections=selections,
    )
    return main._price_factor(boq, schema, rates["direct_cost_lkr"]), rates, schema


@pytest.fixture
def request_dict(sample_building_schema):
    d = dict(sample_building_schema)
    d.pop("rooms")  # BuildingSchema uses its own RoomCounts default
    return d


class TestPriceFactor:
    def test_reference_request_has_factor_one(self, request_dict):
        # grade defaults, no escalation: priced exactly like the training data
        factor, _, _ = _factor(request_dict, target_date="2024-10-01")
        assert factor == pytest.approx(1.0, rel=1e-9)

    def test_escalation_carries_through(self, request_dict):
        factor, rates, _ = _factor(request_dict, target_date="2025-10-01")
        assert factor == pytest.approx(rates["escalation_factor"], rel=1e-4)
        assert factor == pytest.approx(1 + 0.008 * 12, rel=1e-4)

    def test_dearer_material_raises_factor(self, request_dict):
        default, _, _ = _factor(request_dict, target_date="2024-10-01")
        timber, _, _ = _factor(
            request_dict, target_date="2024-10-01",
            materials={"floor_tile_sqm": "timber_flooring"},
        )
        assert timber > default

    def test_total_ratio_equals_factor(self, request_dict):
        # risk and on-costs multiply the direct cost, so totals scale by the same factor
        factor, rates, schema = _factor(
            request_dict, target_date="2026-01-01", finish_grade="luxury",
            materials={"door_count": "tempered_glass_12mm"},
        )
        d = schema.to_dict()
        risk = RiskScorer().score(d, d, schema.finish_grade)["total_risk_pct"]
        total = ContingencyCalculator().calculate(rates["direct_cost_lkr"], risk)
        reference_direct = rates["direct_cost_lkr"] / factor
        reference_total = ContingencyCalculator().calculate(reference_direct, risk)
        assert total["grand_total_lkr"] / reference_total["grand_total_lkr"] == pytest.approx(
            factor, rel=1e-6
        )
