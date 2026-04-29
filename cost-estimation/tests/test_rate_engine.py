"""Tests for Layer 2: district multipliers, price escalation, and rate engine."""

import pytest
from datetime import date

from layers.layer2_rate_engine.district_multiplier import DistrictMultiplier
from layers.layer2_rate_engine.price_escalation import PriceEscalationModel
from layers.layer2_rate_engine.rate_engine import RateEngine
from layers.layer2_rate_engine.ictad_loader import ICTADLoader


# ---------------------------------------------------------------------------
# DistrictMultiplier
# ---------------------------------------------------------------------------

class TestDistrictMultiplier:
    def setup_method(self):
        self.dm = DistrictMultiplier()

    def test_colombo_is_baseline_1_00(self):
        assert self.dm.get_multiplier("Colombo") == 1.00

    def test_mullaitivu_is_highest(self):
        assert self.dm.get_multiplier("Mullaitivu") == 1.22

    def test_gampaha_is_1_02(self):
        assert self.dm.get_multiplier("Gampaha") == 1.02

    def test_unknown_district_returns_1_05(self):
        assert self.dm.get_multiplier("Atlantis") == 1.05

    def test_apply_multiplies_rate(self):
        rate = 10_000.0
        result = self.dm.apply(rate, "Kandy")
        assert result == pytest.approx(10_000.0 * 1.05, rel=1e-6)

    def test_all_districts_returns_list(self):
        districts = self.dm.all_districts
        assert "Colombo" in districts
        assert "Vavuniya" in districts
        assert len(districts) >= 17  # at least the 17 specified

    def test_custom_multipliers_override_defaults(self):
        dm = DistrictMultiplier(custom_multipliers={"Colombo": 1.50})
        assert dm.get_multiplier("Colombo") == 1.50

    def test_all_multipliers_gte_1(self):
        for district, mult in self.dm.as_dict().items():
            assert mult >= 1.00, f"{district} multiplier {mult} < 1.00"


# ---------------------------------------------------------------------------
# PriceEscalationModel
# ---------------------------------------------------------------------------

class TestPriceEscalationModel:
    def setup_method(self):
        self.model = PriceEscalationModel()

    def test_same_date_returns_base_rate(self):
        result = self.model.predict_escalation(100_000, "2025-01-01", "2025-01-01")
        assert result == pytest.approx(100_000.0, rel=1e-6)

    def test_past_target_date_returns_base_rate(self):
        result = self.model.predict_escalation(100_000, "2025-06-01", "2025-01-01")
        assert result == pytest.approx(100_000.0, rel=1e-6)

    def test_12_months_applies_approx_9_6_percent(self):
        base = 100_000.0
        result = self.model.predict_escalation(base, "2024-01-01", "2025-01-01")
        expected = base * (1 + 0.008 * 12)
        assert result == pytest.approx(expected, rel=1e-3)

    def test_escalation_factor_gt_1_for_future_date(self):
        factor = self.model.escalation_factor("2024-01-01", "2025-01-01")
        assert factor > 1.0

    def test_custom_monthly_rate(self):
        model = PriceEscalationModel(monthly_rate=0.01)
        result = model.predict_escalation(100_000, "2024-01-01", "2024-07-01")
        expected = 100_000 * (1 + 0.01 * 6)
        assert result == pytest.approx(expected, rel=1e-3)

    def test_accepts_date_objects(self):
        result = self.model.predict_escalation(
            50_000, date(2024, 1, 1), date(2025, 1, 1)
        )
        assert result > 50_000

    def test_accepts_iso_string(self):
        result = self.model.predict_escalation(50_000, "2024-01-01", "2025-01-01")
        assert isinstance(result, float)


# ---------------------------------------------------------------------------
# ICTADLoader
# ---------------------------------------------------------------------------

class TestICTADLoader:
    def setup_method(self):
        self.loader = ICTADLoader()

    def test_load_all_returns_dict(self):
        rates = self.loader.load_all()
        assert isinstance(rates, dict)
        assert len(rates) > 0

    def test_fallback_rates_include_rc_slab(self):
        rates = self.loader.load_all()
        assert "rc_slab_m3" in rates

    def test_get_rate_returns_positive_float(self):
        rate = self.loader.get_rate("rc_slab_m3")
        assert isinstance(rate, float)
        assert rate > 0

    def test_get_rate_unknown_key_returns_zero(self):
        rate = self.loader.get_rate("nonexistent_item_xyz")
        assert rate == 0.0

    def test_district_view_includes_base_rate(self):
        view = self.loader.get_rates_for_district_view("Kandy")
        assert all("base_rate_lkr" in item for item in view)


# ---------------------------------------------------------------------------
# RateEngine integration
# ---------------------------------------------------------------------------

class TestRateEngine:
    def setup_method(self):
        self.engine = RateEngine()

    def _make_boq(self):
        from layers.layer1_boq.boq_engine import BOQEngine
        schema = {
            "footprint_sqm": 150.0, "perimeter": 50.0, "floors": 2,
            "floor_height": 3.0, "wall_height": 3.0, "excavation_depth": 1.5,
            "finish_grade": "mid", "bathroom_count": 2, "room_count": 5,
            "rooms": {"living_room": 1, "bedroom": 2, "bathroom": 2, "kitchen": 1},
        }
        return BOQEngine().run(schema)

    def test_price_boq_returns_direct_cost(self):
        boq = self._make_boq()
        result = self.engine.price_boq(boq, district="Colombo")
        assert result["direct_cost_lkr"] > 0

    def test_higher_multiplier_district_costs_more(self):
        boq = self._make_boq()
        colombo = self.engine.price_boq(boq, district="Colombo")
        mullaitivu = self.engine.price_boq(boq, district="Mullaitivu")
        assert mullaitivu["direct_cost_lkr"] > colombo["direct_cost_lkr"]

    def test_escalation_increases_cost(self):
        boq = self._make_boq()
        today = self.engine.price_boq(boq, district="Colombo",
                                       base_date="2024-01-01", target_date="2024-01-01")
        future = self.engine.price_boq(boq, district="Colombo",
                                        base_date="2024-01-01", target_date="2026-01-01")
        assert future["direct_cost_lkr"] > today["direct_cost_lkr"]

    def test_get_district_rates_returns_district_adjusted_rates(self):
        result = self.engine.get_district_rates("Kandy")
        assert result["multiplier"] == 1.05
        assert len(result["rates"]) > 0
        for item in result["rates"]:
            assert "district_adjusted_rate_lkr" in item

    def test_trade_breakdown_contains_line_cost(self):
        boq = self._make_boq()
        result = self.engine.price_boq(boq, district="Colombo")
        for key, entry in result["trade_breakdown"].items():
            assert "line_cost_lkr" in entry
