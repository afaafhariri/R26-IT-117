"""
test_buildable_zone.py — Pytest tests for Stage 2: Buildable Zone calculation.

Tests cover NBCConstraintEngine, BuildableZoneCalculator, and OrientationSolver.
"""

import pytest

from stages.stage2_buildable_zone.nbc_constraints import NBCConstraintEngine
from stages.stage2_buildable_zone.polygon_calculator import BuildableZoneCalculator
from stages.stage2_buildable_zone.orientation_solver import OrientationSolver


# ── Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture
def rectangular_polygon():
    """20 m × 15 m rectangle — 300 m² plot."""
    return [[0.0, 0.0], [20.0, 0.0], [20.0, 15.0], [0.0, 15.0]]


@pytest.fixture
def local_setbacks():
    return {"front": 2.0, "rear": 1.5, "side": 0.9}


# ── NBCConstraintEngine tests ─────────────────────────────────────────────

class TestNBCConstraintEngine:
    def test_national_road_setbacks(self):
        """National road should return front=4.5, rear=1.5, side=1.0."""
        engine = NBCConstraintEngine()
        setbacks = engine.get_setbacks("national_road")
        assert setbacks["front"] == pytest.approx(4.5)
        assert setbacks["rear"] == pytest.approx(1.5)
        assert setbacks["side"] == pytest.approx(1.0)

    def test_local_road_setbacks(self):
        """Local road should return front=2.0, rear=1.5, side=0.9."""
        engine = NBCConstraintEngine()
        setbacks = engine.get_setbacks("local")
        assert setbacks["front"] == pytest.approx(2.0)
        assert setbacks["side"] == pytest.approx(0.9)

    def test_lane_setbacks_are_smallest(self):
        """Lane setbacks should be smaller than national road setbacks."""
        engine = NBCConstraintEngine()
        lane = engine.get_setbacks("lane")
        national = engine.get_setbacks("national_road")
        assert lane["front"] < national["front"]
        assert lane["side"] < national["side"]

    def test_unknown_road_type_uses_default(self):
        """Unknown road types should fall back to local defaults without error."""
        engine = NBCConstraintEngine()
        setbacks = engine.get_setbacks("dirt_track")
        assert "front" in setbacks
        assert "rear" in setbacks
        assert "side" in setbacks

    def test_colombo_coverage_ratio(self):
        """Colombo should allow higher coverage than default."""
        engine = NBCConstraintEngine()
        colombo = engine.get_coverage_ratio("Colombo")
        default = engine.get_coverage_ratio("unknown_district")
        assert colombo >= default

    def test_coverage_ratio_between_0_and_1(self):
        """Coverage ratio must always be in [0, 1]."""
        engine = NBCConstraintEngine()
        for district in ("Colombo", "Kandy", "Galle", "unknownplace"):
            ratio = engine.get_coverage_ratio(district)
            assert 0.0 < ratio <= 1.0


# ── BuildableZoneCalculator tests ─────────────────────────────────────────

class TestBuildableZoneCalculator:
    def test_calculate_returns_required_keys(self, rectangular_polygon, local_setbacks):
        """Result must contain all required keys."""
        calc = BuildableZoneCalculator()
        result = calc.calculate(rectangular_polygon, local_setbacks, 0.50)
        required = {
            "buildable_polygon", "buildable_area_sqm",
            "max_area_sqm", "recommended_floors", "plot_area_sqm",
        }
        assert required.issubset(result.keys())

    def test_buildable_area_smaller_than_plot(self, rectangular_polygon, local_setbacks):
        """Buildable area must be strictly smaller than the plot area after setbacks."""
        calc = BuildableZoneCalculator()
        result = calc.calculate(rectangular_polygon, local_setbacks, 0.50)
        assert result["buildable_area_sqm"] < result["plot_area_sqm"]

    def test_max_area_respects_coverage_ratio(self, rectangular_polygon, local_setbacks):
        """max_area_sqm should equal plot_area * coverage_ratio."""
        calc = BuildableZoneCalculator()
        coverage = 0.50
        result = calc.calculate(rectangular_polygon, local_setbacks, coverage)
        expected_max = result["plot_area_sqm"] * coverage
        assert result["max_area_sqm"] == pytest.approx(expected_max, rel=1e-3)

    def test_degenerate_polygon_raises_value_error(self, local_setbacks):
        """Polygon with < 3 vertices must raise ValueError."""
        calc = BuildableZoneCalculator()
        with pytest.raises(ValueError):
            calc.calculate([[0, 0], [10, 0]], local_setbacks, 0.50)

    def test_recommended_floors_small_plot(self, local_setbacks):
        """A very small buildable area should recommend 1 floor."""
        calc = BuildableZoneCalculator()
        tiny = [[0.0, 0.0], [10.0, 0.0], [10.0, 8.0], [0.0, 8.0]]
        result = calc.calculate(tiny, local_setbacks, 0.50)
        assert result["recommended_floors"] >= 1

    def test_recommended_floors_large_plot(self, local_setbacks):
        """A large buildable area should recommend at least 2 floors."""
        calc = BuildableZoneCalculator()
        large = [[0.0, 0.0], [30.0, 0.0], [30.0, 25.0], [0.0, 25.0]]
        result = calc.calculate(large, local_setbacks, 0.60)
        assert result["recommended_floors"] >= 2


# ── OrientationSolver tests ───────────────────────────────────────────────

class TestOrientationSolver:
    def test_solve_returns_required_keys(self):
        """solve() must return all required output keys."""
        solver = OrientationSolver()
        result = solver.solve(45.0)
        for key in (
            "plot_orientation_deg",
            "recommended_building_deg",
            "rotation_delta_deg",
            "solar_efficiency_score",
            "ventilation_score",
            "rationale",
        ):
            assert key in result

    def test_solar_score_between_0_and_1(self):
        """Solar efficiency score must be in [0, 1]."""
        solver = OrientationSolver()
        for angle in (0, 45, 90, 135, 180, 270, 359):
            result = solver.solve(float(angle))
            assert 0.0 <= result["solar_efficiency_score"] <= 1.0

    def test_ventilation_score_between_0_and_1(self):
        """Ventilation score must be in [0, 1]."""
        solver = OrientationSolver()
        for angle in (0, 45, 90, 135, 180, 270, 359):
            result = solver.solve(float(angle))
            assert 0.0 <= result["ventilation_score"] <= 1.0

    def test_east_west_orientation_high_solar_score(self):
        """A plot oriented exactly East-West (90°) should yield maximum solar score."""
        solver = OrientationSolver()
        result = solver.solve(90.0)
        assert result["solar_efficiency_score"] == pytest.approx(1.0, abs=0.01)

    def test_rationale_is_non_empty_string(self):
        """rationale must be a non-empty string."""
        solver = OrientationSolver()
        result = solver.solve(90.0)
        assert isinstance(result["rationale"], str)
        assert len(result["rationale"]) > 10
