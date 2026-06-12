"""Tests for Layer 1 BOQ calculators and the BOQ Engine."""

import pytest

from layers.layer1_boq.structural_boq import StructuralBOQ
from layers.layer1_boq.finishing_boq import FinishingBOQ
from layers.layer1_boq.services_boq import ServicesBOQ
from layers.layer1_boq.boq_engine import BOQEngine


# ---------------------------------------------------------------------------
# StructuralBOQ
# ---------------------------------------------------------------------------

class TestStructuralBOQ:
    def setup_method(self):
        self.boq = StructuralBOQ()

    def test_foundation_excavation_uses_perimeter_and_depth(self, sample_building_schema):
        result = self.boq.calculate(sample_building_schema)
        expected = 50.0 * 1.5 * 0.6
        assert result["foundation_excavation_m3"] == pytest.approx(expected, rel=1e-3)

    def test_blinding_concrete_formula(self, sample_building_schema):
        result = self.boq.calculate(sample_building_schema)
        expected = 50.0 * 0.6 * 0.05
        assert result["blinding_concrete_m3"] == pytest.approx(expected, rel=1e-3)

    def test_rc_slab_scales_with_floors(self, sample_building_schema):
        result_2f = self.boq.calculate(sample_building_schema)
        single = dict(sample_building_schema)
        single["floors"] = 1
        result_1f = self.boq.calculate(single)
        assert result_2f["rc_slab_m3"] == pytest.approx(result_1f["rc_slab_m3"] * 2, rel=1e-3)

    def test_roof_area_is_1_3x_footprint(self, sample_building_schema):
        result = self.boq.calculate(sample_building_schema)
        assert result["roof_area_sqm"] == pytest.approx(150.0 * 1.30, rel=1e-3)

    def test_external_brickwork_reduced_by_openings(self, sample_building_schema):
        schema_no_openings = dict(sample_building_schema)
        schema_no_openings["openings_sqm"] = 0.0
        result_closed = self.boq.calculate(schema_no_openings)
        result_open = self.boq.calculate(sample_building_schema)
        assert result_closed["external_brickwork_m3"] > result_open["external_brickwork_m3"]

    def test_all_required_keys_present(self, sample_building_schema):
        result = self.boq.calculate(sample_building_schema)
        required = {
            "foundation_excavation_m3", "blinding_concrete_m3",
            "foundation_concrete_m3", "rc_columns_m3", "rc_slab_m3",
            "external_brickwork_m3", "internal_blockwork_m3", "roof_area_sqm",
        }
        assert required.issubset(result.keys())

    def test_zero_footprint_returns_zeros(self):
        schema = {"footprint_sqm": 0.0, "perimeter": 0.0, "floors": 1}
        result = self.boq.calculate(schema)
        assert result["rc_slab_m3"] == 0.0
        assert result["roof_area_sqm"] == 0.0


# ---------------------------------------------------------------------------
# FinishingBOQ
# ---------------------------------------------------------------------------

class TestFinishingBOQ:
    def setup_method(self):
        self.boq = FinishingBOQ()

    def test_luxury_floor_tile_greater_than_economy(self, sample_building_schema):
        economy = self.boq.calculate(sample_building_schema, "economy")
        luxury = self.boq.calculate(sample_building_schema, "luxury")
        assert luxury["floor_tile_sqm"] > economy["floor_tile_sqm"]

    def test_luxury_ceiling_greater_than_mid(self, sample_building_schema):
        mid = self.boq.calculate(sample_building_schema, "mid")
        luxury = self.boq.calculate(sample_building_schema, "luxury")
        assert luxury["ceiling_sqm"] > mid["ceiling_sqm"]

    def test_unknown_grade_falls_back_to_mid(self, sample_building_schema):
        mid = self.boq.calculate(sample_building_schema, "mid")
        unknown = self.boq.calculate(sample_building_schema, "PREMIUM")
        assert unknown["floor_tile_sqm"] == mid["floor_tile_sqm"]

    def test_door_count_at_least_one(self, sample_building_schema):
        result = self.boq.calculate(sample_building_schema, "economy")
        assert result["door_count"] >= 1

    def test_all_required_keys_present(self, sample_building_schema):
        result = self.boq.calculate(sample_building_schema, "mid")
        required = {"floor_tile_sqm", "wall_plaster_sqm", "ceiling_sqm",
                    "door_count", "window_count", "paint_sqm", "finish_grade"}
        assert required.issubset(result.keys())

    def test_finish_grade_key_matches_input(self, sample_building_schema):
        for grade in ("economy", "mid", "luxury"):
            result = self.boq.calculate(sample_building_schema, grade)
            assert result["finish_grade"] == grade


# ---------------------------------------------------------------------------
# ServicesBOQ
# ---------------------------------------------------------------------------

class TestServicesBOQ:
    def setup_method(self):
        self.boq = ServicesBOQ()

    def test_living_room_contributes_8_points(self):
        result = self.boq.calculate({"living_room": 1})
        # 8 (living) + 6 (distribution board overhead)
        assert result["electrical_points"] >= 8

    def test_kitchen_contributes_8_points(self):
        result_with = self.boq.calculate({"kitchen": 1})
        result_without = self.boq.calculate({})
        assert result_with["electrical_points"] > result_without["electrical_points"]

    def test_bathroom_plumbing_fixtures_scale_with_count(self):
        result_1 = self.boq.calculate({"bathroom": 1})
        result_2 = self.boq.calculate({"bathroom": 2})
        assert result_2["total_plumbing_fixtures"] > result_1["total_plumbing_fixtures"]

    def test_empty_rooms_returns_zeros(self):
        result = self.boq.calculate({})
        assert result["electrical_points"] == 0
        assert result["total_plumbing_fixtures"] == 0

    def test_hose_bibs_always_present_when_rooms_supplied(self):
        result = self.boq.calculate({"bedroom": 1})
        assert result["plumbing_fixtures"].get("hose_bib", 0) == 2

    def test_multiple_room_types_accumulate_points(self):
        rooms = {"living_room": 1, "bedroom": 2, "bathroom": 1, "kitchen": 1}
        result = self.boq.calculate(rooms)
        # 8 + 4*2 + 3 + 8 = 27, plus 6 fixed = 33
        assert result["electrical_points"] == 33


# ---------------------------------------------------------------------------
# BOQEngine integration
# ---------------------------------------------------------------------------

class TestBOQEngine:
    def setup_method(self):
        self.engine = BOQEngine()

    def test_run_returns_all_sections(self, sample_building_schema):
        result = self.engine.run(sample_building_schema)
        assert {"structural", "finishing", "services", "summary"}.issubset(result.keys())

    def test_summary_contains_total_concrete(self, sample_building_schema):
        result = self.engine.run(sample_building_schema)
        assert result["summary"]["total_concrete_m3"] > 0

    def test_steel_estimate_is_positive(self, sample_building_schema):
        result = self.engine.run(sample_building_schema)
        assert result["summary"]["steel_kg_estimate"] > 0

    def test_finish_grade_propagated(self, sample_building_schema):
        result = self.engine.run(sample_building_schema)
        assert result["summary"]["finish_grade"] == "mid"
