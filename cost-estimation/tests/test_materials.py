"""Tests for the material catalog, variant-aware pricing, and scraper logic."""

from datetime import date, timedelta
from pathlib import Path

import pytest

from layers.layer1_boq.boq_engine import BOQEngine
from layers.layer2_rate_engine.material_catalog import MaterialCatalog
from layers.layer2_rate_engine.rate_engine import RateEngine
from scripts.scrape_stockpile import (
    CATEGORY_RULES,
    classify,
    parse_products,
    reject_outliers,
)


# ---------------------------------------------------------------------------
# MaterialCatalog
# ---------------------------------------------------------------------------

class TestMaterialCatalog:
    def test_loads_all_parts(self):
        catalog = MaterialCatalog()
        parts = catalog.parts()
        assert set(parts) == {
            "door_count", "window_count", "roof_area_sqm",
            "floor_tile_sqm", "ceiling_sqm",
        }

    def test_each_part_has_2_to_5_variants(self):
        catalog = MaterialCatalog()
        for part in catalog.parts():
            assert 2 <= len(catalog.variants(part)) <= 5, part

    def test_variants_sorted_cheapest_first(self):
        catalog = MaterialCatalog()
        rates = [v["rate_lkr"] for v in catalog.variants("door_count")]
        assert rates == sorted(rates)

    def test_get_known_and_unknown(self):
        catalog = MaterialCatalog()
        entry = catalog.get("door_count", "plywood_flush")
        assert entry is not None and entry["rate_lkr"] > 0
        assert catalog.get("door_count", "no_such_material") is None
        assert catalog.get("no_such_part", "plywood_flush") is None

    def test_fresh_overlay_updates_rate(self, tmp_path):
        overlay = tmp_path / "current_prices.csv"
        overlay.write_text(
            "part_key,material_key,supply_rate_lkr,sample_count,last_updated,source\n"
            f"door_count,plywood_flush,20000.00,5,{date.today()},test\n"
        )
        catalog = MaterialCatalog(overlay_csv=overlay)
        entry = catalog.get("door_count", "plywood_flush")
        # 20000 supply + 12000 seed install cost
        assert entry["rate_lkr"] == 32000.00
        assert entry["rate_source"] == "test"

    def test_stale_overlay_ignored(self, tmp_path):
        old = date.today() - timedelta(days=90)
        overlay = tmp_path / "current_prices.csv"
        overlay.write_text(
            "part_key,material_key,supply_rate_lkr,sample_count,last_updated,source\n"
            f"door_count,plywood_flush,20000.00,5,{old},test\n"
        )
        catalog = MaterialCatalog(overlay_csv=overlay, stale_days=45)
        entry = catalog.get("door_count", "plywood_flush")
        assert entry["rate_lkr"] == 26000.00  # seed rate unchanged
        assert entry["rate_source"] == "seed_2024q4"

    def test_missing_overlay_is_fine(self, tmp_path):
        catalog = MaterialCatalog(overlay_csv=tmp_path / "does_not_exist.csv")
        assert catalog.get("door_count", "solid_timber_teak")["rate_lkr"] == 45000.00


# ---------------------------------------------------------------------------
# RateEngine material selection
# ---------------------------------------------------------------------------

@pytest.fixture
def boq(sample_building_schema):
    return BOQEngine().run(sample_building_schema)


class TestRateEngineMaterials:
    def test_no_selection_is_backward_compatible(self, boq):
        engine = RateEngine()
        base = engine.price_boq(boq, district="Colombo", target_date="2025-06-01")
        with_empty = engine.price_boq(
            boq, district="Colombo", target_date="2025-06-01", material_selections={}
        )
        assert base["direct_cost_lkr"] == with_empty["direct_cost_lkr"]
        assert base["trade_breakdown"] == with_empty["trade_breakdown"]
        assert base["material_selections"] == {}

    def test_selection_changes_line_cost(self, boq):
        engine = RateEngine()
        baseline = engine.price_boq(boq, district="Colombo", target_date="2025-06-01")
        cheaper = engine.price_boq(
            boq, district="Colombo", target_date="2025-06-01",
            material_selections={"door_count": "plywood_flush"},
        )
        # Plywood (26k) is cheaper than the ICTAD solid timber baseline (45k)
        assert (cheaper["trade_breakdown"]["door_count"]["line_cost_lkr"]
                < baseline["trade_breakdown"]["door_count"]["line_cost_lkr"])
        assert cheaper["direct_cost_lkr"] < baseline["direct_cost_lkr"]
        assert cheaper["trade_breakdown"]["door_count"]["material"] == "plywood_flush"
        assert cheaper["material_selections"] == {"door_count": "plywood_flush"}

    def test_unknown_material_falls_back_to_ictad(self, boq):
        engine = RateEngine()
        baseline = engine.price_boq(boq, district="Colombo", target_date="2025-06-01")
        result = engine.price_boq(
            boq, district="Colombo", target_date="2025-06-01",
            material_selections={"door_count": "unobtainium"},
        )
        assert result["direct_cost_lkr"] == baseline["direct_cost_lkr"]
        assert result["material_selections"] == {}

    def test_district_multiplier_applies_to_material_rates(self, boq):
        engine = RateEngine()
        colombo = engine.price_boq(
            boq, district="Colombo", target_date="2025-06-01",
            material_selections={"door_count": "plywood_flush"},
        )
        remote = engine.price_boq(
            boq, district="Mullaitivu", target_date="2025-06-01",
            material_selections={"door_count": "plywood_flush"},
        )
        assert (remote["trade_breakdown"]["door_count"]["adjusted_rate_lkr"]
                > colombo["trade_breakdown"]["door_count"]["adjusted_rate_lkr"])

    def test_alternatives_present_for_boq_parts(self, boq):
        engine = RateEngine()
        result = engine.price_boq(
            boq, district="Colombo", target_date="2025-06-01",
            material_selections={"door_count": "solid_timber_teak"},
        )
        alts = result["material_alternatives"]
        assert "door_count" in alts
        door_alts = alts["door_count"]
        assert 2 <= len(door_alts) <= 5
        selected = [a for a in door_alts if a["is_selected"]]
        assert len(selected) == 1
        assert selected[0]["material"] == "solid_timber_teak"
        # Line costs scale with quantity
        qty = result["trade_breakdown"]["door_count"]["quantity"]
        for alt in door_alts:
            assert alt["line_cost_lkr"] == pytest.approx(alt["unit_rate_lkr"] * qty, abs=0.5)

    def test_catalog_view_shape(self):
        view = RateEngine().get_material_catalog_view()
        assert set(view) == {
            "door_count", "window_count", "roof_area_sqm",
            "floor_tile_sqm", "ceiling_sqm",
        }
        for variants in view.values():
            for v in variants:
                assert {"material", "description", "unit", "rate_lkr",
                        "rate_source", "last_updated"} <= set(v)


# ---------------------------------------------------------------------------
# Scraper pure functions (no network)
# ---------------------------------------------------------------------------

DOOR_RULES = CATEGORY_RULES["/en/door-windows.html"]
ROOF_RULES = CATEGORY_RULES["/en/roofing-ceiling.html"]


class TestScraperClassification:
    @pytest.mark.parametrize("name,expected", [
        ("Armee Teak Wooden Door 2 Panels BA005", ("door_count", "solid_timber_teak")),
        ("ICC Timber Plywood Doors 7ft x 3ft", ("door_count", "plywood_flush")),
        ("Sealcore Painted Wood Composite Door", ("door_count", "wood_composite")),
        ("Tempered Glass Door 12mm", ("door_count", "tempered_glass_12mm")),
    ])
    def test_door_classification(self, name, expected):
        result = classify(name, DOOR_RULES)
        assert result is not None
        assert result[:2] == expected

    def test_accessories_skipped(self):
        assert classify("Armee Teak Wooden Door Frame", DOOR_RULES) is None
        assert classify("Stainless Steel Door Handle", DOOR_RULES) is None

    def test_unmatched_returns_none(self):
        assert classify("Random Widget 3000", DOOR_RULES) is None

    def test_roofing_sheets_are_history_only(self):
        result = classify("EL Toro Fiber Cement sheets 8' x 4'", ROOF_RULES)
        assert result is not None
        assert result[2] is None  # no unit factor -> never written to overlay

    def test_ceiling_tile_unit_factor(self):
        result = classify("Daiken Mineral Fiber Ceiling Tiles 2' x 2'", ROOF_RULES)
        assert result is not None
        part, material, factor = result
        assert (part, material) == ("ceiling_sqm", "mineral_fiber_tile")
        assert factor == pytest.approx(1 / 0.3716)


class TestScraperParsing:
    SAMPLE_HTML = """
    <ol class="products list items product-items">
      <li class="item product product-item">
        <a class="product-item-link" href="https://stockpile.lk/en/teak-door.html">
          Armee Teak Wooden Door 2 Panels</a>
        <span data-price-amount="28000" data-price-type="finalPrice">
          <span class="price">Rs. 28,000.00</span></span>
      </li>
      <li class="item product product-item">
        <a class="product-item-link" href="https://stockpile.lk/en/plywood-door.html">
          ICC Timber Plywood Doors 7ft x 3ft</a>
        <span class="price">Rs. 13,559.32</span>
      </li>
      <li class="item product product-item">
        <a class="product-item-link" href="https://stockpile.lk/en/free-sample.html">
          Zero Price Item</a>
        <span class="price">Rs. 0.00</span>
      </li>
    </ol>
    """

    def test_parse_products(self):
        products = parse_products(self.SAMPLE_HTML)
        assert len(products) == 2  # zero-priced item dropped
        assert products[0]["name"] == "Armee Teak Wooden Door 2 Panels"
        assert products[0]["price"] == 28000.0          # from data-price-amount
        assert products[1]["price"] == 13559.32          # from Rs. text fallback

    def test_parse_empty_html(self):
        assert parse_products("<html><body>nothing here</body></html>") == []


class TestOutlierRejection:
    def test_small_samples_kept(self):
        assert reject_outliers([100.0, 200.0]) == [100.0, 200.0]

    def test_extreme_outlier_dropped(self):
        prices = [26000.0, 28000.0, 30000.0, 500000.0]
        kept = reject_outliers(prices)
        assert 500000.0 not in kept
        assert len(kept) == 3

    def test_normal_spread_kept(self):
        prices = [26000.0, 28000.0, 30000.0, 45000.0]
        assert reject_outliers(prices) == prices
