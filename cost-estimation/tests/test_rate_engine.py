"""Tests for Layer 2: price escalation, ICTAD loading, and rate engine."""

import pytest
from datetime import date

from layers.layer2_rate_engine.price_escalation import PriceEscalationModel
from layers.layer2_rate_engine.rate_engine import RateEngine
from layers.layer2_rate_engine.ictad_loader import ICTADLoader


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

    def test_rates_view_includes_base_rate(self):
        view = self.loader.get_rates_view()
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
        result = self.engine.price_boq(boq)
        assert result["direct_cost_lkr"] > 0

    def test_escalation_increases_cost(self):
        boq = self._make_boq()
        today = self.engine.price_boq(boq,
                                       base_date="2024-01-01", target_date="2024-01-01")
        future = self.engine.price_boq(boq,
                                        base_date="2024-01-01", target_date="2026-01-01")
        assert future["direct_cost_lkr"] > today["direct_cost_lkr"]

    def test_get_rates_returns_schedule(self):
        result = self.engine.get_rates()
        assert len(result["rates"]) > 0
        for item in result["rates"]:
            assert "base_rate_lkr" in item

    def test_trade_breakdown_contains_line_cost(self):
        boq = self._make_boq()
        result = self.engine.price_boq(boq)
        for key, entry in result["trade_breakdown"].items():
            assert "line_cost_lkr" in entry
