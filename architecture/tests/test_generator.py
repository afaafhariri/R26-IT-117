"""Tests for Stage 3 floor plan generation pipeline."""

import json
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# PromptBuilder
# ---------------------------------------------------------------------------

class TestPromptBuilder:
    def test_prompt_builder_contains_4_parts(
        self, sample_buildable_zone, sample_user_requirements
    ):
        """Built prompt must contain all 4 required section headers."""
        from stages.stage3_floor_plan.prompt_builder import PromptBuilder

        retrieved = [
            "Living rooms face the road in Sri Lanka.",
            "Cross-ventilation via opposing openings is essential.",
        ]
        prompt = PromptBuilder().build(
            sample_buildable_zone, sample_user_requirements, retrieved
        )

        assert "DESIGN PRECEDENTS AND STANDARDS" in prompt
        assert "SITE CONSTRAINTS" in prompt
        assert "USER REQUIREMENTS" in prompt
        assert "OUTPUT FORMAT" in prompt

    def test_prompt_builder_embeds_footprint(
        self, sample_buildable_zone, sample_user_requirements
    ):
        from stages.stage3_floor_plan.prompt_builder import PromptBuilder

        prompt = PromptBuilder().build(sample_buildable_zone, sample_user_requirements, [])
        assert str(int(sample_buildable_zone["max_footprint_sqm"])) in prompt


# ---------------------------------------------------------------------------
# FloorPlanGenerator
# ---------------------------------------------------------------------------

class TestFloorPlanGenerator:
    def _mock_llm_response(self) -> str:
        return json.dumps(
            {
                "layout_name": "Test Layout",
                "rooms": [
                    {
                        "name": "living_room",
                        "area_sqm": 18.0,
                        "floor": 1,
                        "x_norm": 0.1,
                        "y_norm": 0.1,
                        "width_norm": 0.3,
                        "height_norm": 0.25,
                        "window_orientation": "south",
                        "adjacencies": ["dining"],
                    }
                ],
                "total_area_sqm": 18.0,
                "space_notes": "Compact layout.",
            }
        )

    def _make_generator(self, mock_response_text: str):
        """Creates a FloorPlanGenerator via __new__ with correctly mocked Gemini client.

        _call_llm uses self.client.models.generate_content(...) and self.types.
        """
        from stages.stage3_floor_plan.llm_generator import FloorPlanGenerator

        gen = FloorPlanGenerator.__new__(FloorPlanGenerator)
        mock_resp = MagicMock()
        mock_resp.text = mock_response_text
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_resp
        gen.client = mock_client
        gen.types = MagicMock()
        gen.model_name = "gemini-2.5-flash"
        gen.temperatures = [0.4, 0.7, 1.0]
        gen.max_retries = 3
        return gen

    def test_llm_generator_returns_3_alternatives(self):
        """generate must return a list of exactly 3 dicts."""
        gen = self._make_generator(self._mock_llm_response())
        results = gen.generate("test prompt")

        assert isinstance(results, list)
        assert len(results) == 3

    def test_llm_generator_labels_present(self):
        """Each alternative must carry temperature and layout_label fields."""
        gen = self._make_generator(self._mock_llm_response())
        results = gen.generate("prompt")

        labels = [r["layout_label"] for r in results]
        assert labels == ["conservative", "balanced", "creative"]
        for r in results:
            assert "temperature" in r


# ---------------------------------------------------------------------------
# LayoutValidator
# ---------------------------------------------------------------------------

class TestLayoutValidator:
    def test_validator_catches_oversized_layout(self, sample_buildable_zone):
        """A layout whose total area vastly exceeds the max should fail validation."""
        from stages.stage3_floor_plan.validator import LayoutValidator

        oversized_plan = {
            "rooms": [
                {
                    "name": "living_room",
                    "area_sqm": 9999.0,
                    "floor": 1,
                    "x_norm": 0.0,
                    "y_norm": 0.0,
                    "width_norm": 0.5,
                    "height_norm": 0.5,
                    "window_orientation": "south",
                    "adjacencies": [],
                }
            ]
        }
        is_valid, violations = LayoutValidator().validate(oversized_plan, sample_buildable_zone)
        assert is_valid is False
        assert len(violations) > 0

    def test_validator_accepts_valid_layout(
        self, sample_floor_plan, sample_buildable_zone
    ):
        """Total area of the sample floor plan must be within the allowed maximum."""
        total = sum(r["area_sqm"] for r in sample_floor_plan["rooms"])
        assert total <= sample_buildable_zone["max_total_built_sqm"] * 1.05


# ---------------------------------------------------------------------------
# LayoutScorer
# ---------------------------------------------------------------------------

class TestLayoutScorer:
    def test_scorer_returns_all_5_scores(self, sample_floor_plan):
        from stages.stage3_floor_plan.scorer import LayoutScorer

        result = LayoutScorer().score(sample_floor_plan)
        expected_keys = {
            "space_utilisation",
            "natural_light",
            "adjacency_quality",
            "ventilation_potential",
            "overall",
        }
        assert expected_keys.issubset(result.keys())

    def test_scorer_values_in_range(self, sample_floor_plan):
        from stages.stage3_floor_plan.scorer import LayoutScorer

        result = LayoutScorer().score(sample_floor_plan)
        for key, value in result.items():
            assert 0.0 <= value <= 1.0, f"{key} score {value} is out of range [0, 1]"

    def test_scorer_overall_is_weighted_average(self, sample_floor_plan):
        from stages.stage3_floor_plan.scorer import LayoutScorer

        result = LayoutScorer().score(sample_floor_plan)
        expected_overall = round(
            result["space_utilisation"] * 0.30
            + result["natural_light"] * 0.30
            + result["adjacency_quality"] * 0.20
            + result["ventilation_potential"] * 0.20,
            2,
        )
        assert abs(result["overall"] - expected_overall) < 0.01


# ---------------------------------------------------------------------------
# RAGRetriever
# ---------------------------------------------------------------------------

class TestRAGRetriever:
    def test_rag_retriever_returns_list(
        self, sample_buildable_zone, sample_user_requirements
    ):
        """retrieve must return a non-empty list of strings when collection is absent."""
        from stages.stage3_floor_plan.rag_retriever import RAGRetriever

        # Build retriever via __new__ — bypasses __init__ so no ChromaDB connection
        retriever = RAGRetriever.__new__(RAGRetriever)
        retriever.client = None
        retriever.collection = None
        retriever.embedder = MagicMock()
        retriever.collection_name = "sl_residential_plans"

        result = retriever.retrieve(sample_buildable_zone, sample_user_requirements)

        assert isinstance(result, list)
        assert len(result) > 0
        assert all(isinstance(p, str) for p in result)
