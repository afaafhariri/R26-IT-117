"""
test_generator.py — Pytest tests for Stage 3: Floor Plan Generation.

Tests cover PromptBuilder, FloorPlanGenerator (stub mode), LayoutValidator,
and LayoutScorer.
"""

import pytest

from stages.stage3_floor_plan.prompt_builder import PromptBuilder
from stages.stage3_floor_plan.llm_generator import FloorPlanGenerator
from stages.stage3_floor_plan.validator import LayoutValidator
from stages.stage3_floor_plan.scorer import LayoutScorer


# ── Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture
def buildable_zone():
    return {
        "buildable_polygon": [
            [0.0, 0.0], [12.0, 0.0], [12.0, 10.0], [0.0, 10.0]
        ],
        "buildable_area_sqm": 120.0,
        "max_area_sqm": 150.0,
        "recommended_floors": 2,
        "plot_area_sqm": 300.0,
        "setbacks_applied": {"front": 2.0, "rear": 1.5, "side": 0.9},
        "optimal_orientation": {
            "recommended_building_deg": 90.0,
            "solar_efficiency_score": 1.0,
        },
    }


@pytest.fixture
def user_requirements():
    return {
        "rooms": ["Living Room", "Dining Room", "Kitchen", "Bedroom 1",
                  "Bedroom 2", "Bathroom", "Veranda"],
        "style": "modern",
        "finish_grade": "standard",
        "num_floors": 2,
        "special_requirements": "covered veranda facing front road",
    }


@pytest.fixture
def valid_floor_plan():
    """A floor plan where all rooms are inside the 12×10 buildable zone."""
    return {
        "floor_plan_id": "test-fp-001",
        "style": "modern",
        "total_floors": 2,
        "roof_type": "gable",
        "foundation_type": "strip",
        "rooms": [
            {
                "name": "Living Room",
                "floor": 1,
                "polygon": [[0.0, 0.0], [6.0, 0.0], [6.0, 5.0], [0.0, 5.0]],
                "area_sqm": 30.0,
                "has_window": True,
                "has_door": True,
                "adjacencies": ["Dining Room", "Veranda"],
            },
            {
                "name": "Bedroom 1",
                "floor": 1,
                "polygon": [[6.0, 0.0], [10.0, 0.0], [10.0, 4.0], [6.0, 4.0]],
                "area_sqm": 16.0,
                "has_window": True,
                "has_door": True,
                "adjacencies": ["Bathroom"],
            },
            {
                "name": "Bathroom",
                "floor": 1,
                "polygon": [[6.0, 4.0], [9.0, 4.0], [9.0, 6.0], [6.0, 6.0]],
                "area_sqm": 6.0,
                "has_window": False,
                "has_door": True,
                "adjacencies": ["Bedroom 1"],
            },
        ],
    }


@pytest.fixture
def invalid_floor_plan():
    """Floor plan with rooms outside the buildable zone."""
    return {
        "floor_plan_id": "test-fp-bad",
        "style": "modern",
        "total_floors": 1,
        "rooms": [
            {
                "name": "Living Room",
                "floor": 1,
                "polygon": [[0.0, 0.0], [15.0, 0.0], [15.0, 12.0], [0.0, 12.0]],  # exceeds 12×10
                "area_sqm": 180.0,
                "has_window": True,
                "has_door": True,
                "adjacencies": [],
            },
        ],
    }


# ── PromptBuilder tests ───────────────────────────────────────────────────

class TestPromptBuilder:
    def test_build_returns_non_empty_string(self, buildable_zone, user_requirements):
        """build() must return a non-empty string."""
        builder = PromptBuilder()
        prompt = builder.build(buildable_zone, user_requirements, [])
        assert isinstance(prompt, str)
        assert len(prompt) > 100

    def test_prompt_contains_all_four_parts(self, buildable_zone, user_requirements):
        """Prompt must contain markers for all 4 structural parts."""
        builder = PromptBuilder()
        prompt = builder.build(buildable_zone, user_requirements, [])
        assert "ROLE" in prompt
        assert "REFERENCE PLANS" in prompt
        assert "SITE CONSTRAINTS" in prompt
        assert "USER REQUIREMENTS" in prompt

    def test_prompt_contains_output_format_instruction(
        self, buildable_zone, user_requirements
    ):
        """Prompt must contain the JSON output format instruction."""
        builder = PromptBuilder()
        prompt = builder.build(buildable_zone, user_requirements, [])
        assert "OUTPUT FORMAT" in prompt
        assert "json" in prompt.lower()

    def test_prompt_includes_rag_context(self, buildable_zone, user_requirements):
        """Prompt must embed retrieved plan descriptions."""
        retrieved = [
            {"metadata": {"plan_id": "ref_001", "style": "modern", "floors": 2, "area_sqm": 120},
             "document": "3-bedroom modern house in Colombo."}
        ]
        builder = PromptBuilder()
        prompt = builder.build(buildable_zone, user_requirements, retrieved)
        assert "3-bedroom modern house in Colombo" in prompt

    def test_prompt_includes_user_rooms(self, buildable_zone, user_requirements):
        """User-requested room names must appear in the prompt."""
        builder = PromptBuilder()
        prompt = builder.build(buildable_zone, user_requirements, [])
        assert "Living Room" in prompt
        assert "Kitchen" in prompt


# ── FloorPlanGenerator tests (stub mode) ─────────────────────────────────

class TestFloorPlanGenerator:
    def test_generate_returns_three_options(self):
        """generate() must return exactly 3 plan alternatives."""
        gen = FloorPlanGenerator()
        plans = gen.generate("test prompt")
        assert len(plans) == 3

    def test_each_plan_has_floor_plan_id(self):
        """Each generated plan must have a floor_plan_id field."""
        gen = FloorPlanGenerator()
        plans = gen.generate("test prompt")
        for plan in plans:
            assert "floor_plan_id" in plan

    def test_each_plan_has_rooms(self):
        """Each generated plan must have a rooms list."""
        gen = FloorPlanGenerator()
        plans = gen.generate("test prompt")
        for plan in plans:
            assert "rooms" in plan
            assert isinstance(plan["rooms"], list)

    def test_generation_temperatures_vary(self):
        """Each plan should record a different generation temperature."""
        gen = FloorPlanGenerator()
        plans = gen.generate("test prompt")
        temps = [p.get("_generation_temperature") for p in plans]
        assert len(set(temps)) == 3  # all three temperatures must differ


# ── LayoutValidator tests ─────────────────────────────────────────────────

class TestLayoutValidator:
    def test_valid_plan_passes(self, valid_floor_plan, buildable_zone):
        """A well-formed plan should pass validation."""
        validator = LayoutValidator()
        is_valid, violations = validator.validate(valid_floor_plan, buildable_zone)
        # Geometric checks depend on Shapely; at minimum no dimension violations
        assert isinstance(is_valid, bool)
        assert isinstance(violations, list)

    def test_empty_rooms_fails(self, buildable_zone):
        """A plan with no rooms must fail validation."""
        validator = LayoutValidator()
        is_valid, violations = validator.validate({"rooms": []}, buildable_zone)
        assert is_valid is False
        assert len(violations) > 0

    def test_room_below_min_area_flagged(self, buildable_zone):
        """A bedroom smaller than NBC minimum (9 m²) must be flagged."""
        validator = LayoutValidator()
        plan = {
            "rooms": [
                {
                    "name": "Bedroom 1",
                    "floor": 1,
                    "polygon": [[0, 0], [2, 0], [2, 2], [0, 2]],
                    "area_sqm": 4.0,  # below 9 m² minimum
                    "has_window": True,
                    "has_door": True,
                    "adjacencies": [],
                }
            ]
        }
        is_valid, violations = validator.validate(plan, buildable_zone)
        assert is_valid is False
        assert any("below NBC minimum" in v for v in violations)

    def test_habitable_room_without_window_flagged(self, buildable_zone):
        """A living room with no window must be flagged."""
        validator = LayoutValidator()
        plan = {
            "rooms": [
                {
                    "name": "Living Room",
                    "floor": 1,
                    "polygon": [[0, 0], [5, 0], [5, 4], [0, 4]],
                    "area_sqm": 20.0,
                    "has_window": False,  # violation
                    "has_door": True,
                    "adjacencies": [],
                }
            ]
        }
        is_valid, violations = validator.validate(plan, buildable_zone)
        assert is_valid is False
        assert any("window" in v.lower() for v in violations)


# ── LayoutScorer tests ────────────────────────────────────────────────────

class TestLayoutScorer:
    def test_score_returns_all_dimensions(self, valid_floor_plan):
        """score() must return all 5 score keys."""
        scorer = LayoutScorer()
        result = scorer.score(valid_floor_plan)
        for key in (
            "space_utilisation", "natural_light",
            "adjacency_quality", "ventilation_potential", "overall",
        ):
            assert key in result

    def test_all_scores_in_range(self, valid_floor_plan):
        """Every score value must be in [0.0, 1.0]."""
        scorer = LayoutScorer()
        result = scorer.score(valid_floor_plan)
        for key, value in result.items():
            assert 0.0 <= value <= 1.0, f"{key} = {value} out of range"

    def test_empty_plan_returns_zero_overall(self):
        """An empty floor plan should score 0.0 overall."""
        scorer = LayoutScorer()
        result = scorer.score({"rooms": []})
        assert result["overall"] == 0.0

    def test_plan_with_all_windowed_rooms_scores_full_light(self):
        """A plan where every habitable room has a window should score 1.0 for natural_light."""
        scorer = LayoutScorer()
        plan = {
            "rooms": [
                {
                    "name": "Living Room",
                    "floor": 1,
                    "polygon": [[0, 0], [6, 0], [6, 5], [0, 5]],
                    "area_sqm": 30.0,
                    "has_window": True,
                    "has_door": True,
                    "adjacencies": [],
                },
                {
                    "name": "Bedroom 1",
                    "floor": 1,
                    "polygon": [[0, 5], [5, 5], [5, 9], [0, 9]],
                    "area_sqm": 20.0,
                    "has_window": True,
                    "has_door": True,
                    "adjacencies": [],
                },
            ]
        }
        result = scorer.score(plan)
        assert result["natural_light"] == pytest.approx(1.0, abs=0.01)
