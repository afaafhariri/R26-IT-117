"""
llm_generator.py — LLM-based floor plan generation with 3 temperature variants.

Calls the configured LLM provider (OpenAI GPT-4o or Google Gemini) at three
different temperature settings to produce diverse floor plan alternatives.
"""

import os
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

_TEMPERATURES = [0.4, 0.7, 1.0]
_LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai")   # "openai" | "gemini"
_OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
_GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-pro")
_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "4096"))


class FloorPlanGenerator:
    """
    Generates 3 floor plan JSON alternatives by calling the LLM
    at temperature 0.4, 0.7, and 1.0.
    """

    def generate(self, prompt: str) -> list[dict]:
        """
        Make 3 sequential LLM calls and parse the returned JSON floor plans.

        Args:
            prompt: Structured prompt from PromptBuilder.build().

        Returns:
            List of 3 floor plan dicts (or fewer if some calls fail).

        Raises:
            RuntimeError: If all 3 LLM calls fail.
        """
        results: list[dict] = []
        errors: list[str] = []

        for temp in _TEMPERATURES:
            try:
                raw = self._call_llm(prompt, temperature=temp)
                plan = self._parse_response(raw)
                plan["_generation_temperature"] = temp
                results.append(plan)
                logger.info("Generated floor plan at temperature %.1f", temp)
            except Exception as exc:
                logger.warning("LLM call at temperature %.1f failed: %s", temp, exc)
                errors.append(str(exc))
                results.append(self._stub_plan(temp))

        if not results:
            raise RuntimeError(f"All LLM generation calls failed: {errors}")

        return results

    def _call_llm(self, prompt: str, temperature: float) -> str:
        """
        Dispatch to the configured LLM provider and return the raw response text.

        Args:
            prompt:      Full prompt string.
            temperature: Sampling temperature (0.4 | 0.7 | 1.0).

        Returns:
            Raw string response from the LLM.
        """
        if _LLM_PROVIDER == "gemini":
            return self._call_gemini(prompt, temperature)
        return self._call_openai(prompt, temperature)

    @staticmethod
    def _call_openai(prompt: str, temperature: float) -> str:
        """Call OpenAI Chat Completion API."""
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise EnvironmentError("OPENAI_API_KEY environment variable is not set.")

        try:
            from openai import OpenAI  # type: ignore

            client = OpenAI(api_key=api_key)
            response = client.chat.completions.create(
                model=_OPENAI_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=_MAX_TOKENS,
                response_format={"type": "json_object"},
            )
            return response.choices[0].message.content or ""
        except ImportError as exc:
            raise RuntimeError("openai package not installed") from exc

    @staticmethod
    def _call_gemini(prompt: str, temperature: float) -> str:
        """Call Google Gemini GenerativeModel API."""
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise EnvironmentError("GEMINI_API_KEY environment variable is not set.")

        try:
            import google.generativeai as genai  # type: ignore

            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(model_name=_GEMINI_MODEL)
            config = genai.types.GenerationConfig(
                temperature=temperature,
                max_output_tokens=_MAX_TOKENS,
            )
            response = model.generate_content(prompt, generation_config=config)
            return response.text or ""
        except ImportError as exc:
            raise RuntimeError("google-generativeai package not installed") from exc

    @staticmethod
    def _parse_response(raw: str) -> dict:
        """
        Extract JSON from LLM response text.
        Handles responses that wrap JSON in markdown code fences.

        Raises:
            ValueError: If no valid JSON can be parsed.
        """
        text = raw.strip()

        # Strip markdown code fence if present
        if text.startswith("```"):
            lines = text.splitlines()
            inner = "\n".join(
                line for line in lines if not line.startswith("```")
            )
            text = inner.strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"LLM response is not valid JSON: {exc}\nRaw: {raw[:300]}") from exc

    @staticmethod
    def _stub_plan(temperature: float) -> dict:
        """
        Return a placeholder floor plan when the LLM is unavailable.
        TODO: remove once LLM API keys are configured.
        """
        return {
            "floor_plan_id": f"stub-t{int(temperature * 10):02d}",
            "style": "modern",
            "total_floors": 2,
            "rooms": [
                {
                    "name": "Living Room",
                    "floor": 1,
                    "polygon": [[0, 0], [6, 0], [6, 5], [0, 5]],
                    "area_sqm": 30.0,
                    "has_window": True,
                    "has_door": True,
                    "adjacencies": ["Dining Room", "Veranda"],
                },
                {
                    "name": "Bedroom 1",
                    "floor": 1,
                    "polygon": [[6, 0], [10, 0], [10, 4], [6, 4]],
                    "area_sqm": 16.0,
                    "has_window": True,
                    "has_door": True,
                    "adjacencies": ["Bathroom"],
                },
            ],
            "circulation": {"corridors": [], "staircases": []},
            "roof_type": "gable",
            "foundation_type": "strip",
            "_generation_temperature": temperature,
            "_stub": True,
        }
