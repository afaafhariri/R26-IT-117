"""Tests for Stage 2 buildable zone pipeline."""

import pytest


# ---------------------------------------------------------------------------
# NBCConstraintEngine
# ---------------------------------------------------------------------------

class TestNBCConstraintEngine:
    def test_nbc_national_road_setbacks(self):
        from stages.stage2_buildable_zone.nbc_constraints import NBCConstraintEngine

        result = NBCConstraintEngine().get_setbacks("national_road")
        assert result == {"front": 4.5, "rear": 1.5, "side": 1.0}

    def test_nbc_unknown_road_type_falls_back(self):
        from stages.stage2_buildable_zone.nbc_constraints import NBCConstraintEngine

        result = NBCConstraintEngine().get_setbacks("motorway")
        assert result == NBCConstraintEngine().get_setbacks("local")

    def test_nbc_coastal_coverage(self):
        from stages.stage2_buildable_zone.nbc_constraints import NBCConstraintEngine

        ratio = NBCConstraintEngine().get_coverage_ratio("Ampara", is_coastal=True)
        assert ratio == 0.40

    def test_nbc_urban_coverage(self):
        from stages.stage2_buildable_zone.nbc_constraints import NBCConstraintEngine

        ratio = NBCConstraintEngine().get_coverage_ratio("Colombo", is_coastal=False)
        assert ratio == 0.65

    def test_nbc_default_coverage(self):
        from stages.stage2_buildable_zone.nbc_constraints import NBCConstraintEngine

        ratio = NBCConstraintEngine().get_coverage_ratio("Kandy", is_coastal=False)
        assert ratio == 0.50

    def test_nbc_max_floors_by_area(self):
        from stages.stage2_buildable_zone.nbc_constraints import NBCConstraintEngine

        engine = NBCConstraintEngine()
        assert engine.get_max_floors(150, "Kandy") == 1
        assert engine.get_max_floors(300, "Kandy") == 2
        assert engine.get_max_floors(600, "Kandy") == 3


# ---------------------------------------------------------------------------
# BuildableZoneCalculator
# ---------------------------------------------------------------------------

class TestBuildableZoneCalculator:
    _SQUARE_POLYGON = [
        [0.0, 0.0], [100.0, 0.0], [100.0, 100.0], [0.0, 100.0]
    ]
    _SETBACKS = {"front": 3.0, "rear": 1.5, "side": 1.0}

    def test_polygon_calculator_reduces_area(self):
        from stages.stage2_buildable_zone.polygon_calculator import BuildableZoneCalculator

        result = BuildableZoneCalculator().calculate(
            self._SQUARE_POLYGON, self._SETBACKS, 0.5, 2
        )
        assert result["max_footprint_sqm"] < 100.0 * 100.0

    def test_polygon_calculator_output_schema(self):
        from stages.stage2_buildable_zone.polygon_calculator import BuildableZoneCalculator

        result = BuildableZoneCalculator().calculate(
            self._SQUARE_POLYGON, self._SETBACKS, 0.5, 2
        )
        for key in (
            "buildable_polygon",
            "max_footprint_sqm",
            "max_total_built_sqm",
            "recommended_floors",
            "setback_margins",
            "coverage_achieved",
        ):
            assert key in result, f"Missing key: {key}"

    def test_polygon_max_total_built_is_footprint_times_floors(self):
        from stages.stage2_buildable_zone.polygon_calculator import BuildableZoneCalculator

        result = BuildableZoneCalculator().calculate(
            self._SQUARE_POLYGON, self._SETBACKS, 0.5, 2
        )
        assert abs(result["max_total_built_sqm"] - result["max_footprint_sqm"] * 2) < 0.1

    def test_polygon_invalid_input_raises(self):
        """Self-intersecting or degenerate polygon should raise ValueError."""
        from stages.stage2_buildable_zone.polygon_calculator import BuildableZoneCalculator

        # Bowtie (self-intersecting) polygon
        bowtie = [
            [0.0, 0.0], [10.0, 10.0], [10.0, 0.0], [0.0, 10.0]
        ]
        with pytest.raises((ValueError, Exception)):
            BuildableZoneCalculator().calculate(bowtie, self._SETBACKS, 0.5, 1)

    def test_polygon_too_few_vertices_raises(self):
        from stages.stage2_buildable_zone.polygon_calculator import BuildableZoneCalculator

        with pytest.raises(ValueError):
            BuildableZoneCalculator().calculate([[0, 0], [1, 0]], self._SETBACKS, 0.5, 1)


# ---------------------------------------------------------------------------
# OrientationSolver
# ---------------------------------------------------------------------------

class TestOrientationSolver:
    def test_orientation_solver_returns_dict(self, sample_site_schema, sample_buildable_zone):
        from stages.stage2_buildable_zone.orientation_solver import OrientationSolver

        result = OrientationSolver().solve(
            sample_buildable_zone["buildable_polygon"], sample_site_schema
        )
        assert "recommended_orientation_degrees" in result
        assert "entrance_side" in result
        assert "optimal_placement" in result
        assert "solar_notes" in result

    def test_orientation_solver_entrance_side_values(self, sample_site_schema, sample_buildable_zone):
        from stages.stage2_buildable_zone.orientation_solver import OrientationSolver

        result = OrientationSolver().solve(
            sample_buildable_zone["buildable_polygon"], sample_site_schema
        )
        assert result["entrance_side"] in ("north", "south", "east", "west")
        assert 0.0 <= result["recommended_orientation_degrees"] < 360.0
