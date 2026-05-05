"""Gemini API client for multi-temperature floor plan generation."""

import json
import os
import re
import time

from utils.logger import get_logger

_logger = get_logger("llm_generator")

_LAYOUT_LABELS = ["conservative", "balanced", "creative"]


class FloorPlanGenerator:
    """Generates 3 floor plan alternatives using Gemini at different temperatures
    to produce a conservative, balanced, and creative option.
    """

    def __init__(self) -> None:
        import google.generativeai as genai

        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            _logger.warning("GEMINI_API_KEY not set — LLM calls will fail at runtime")

        genai.configure(api_key=api_key)
        self.genai = genai
        self.model = genai.GenerativeModel("gemini-2.0-flash")
        self.temperatures = [0.4, 0.7, 1.0]
        self.max_retries = 3
        _logger.info("FloorPlanGenerator initialised (model=gemini-2.0-flash)")

    def _strip_fences(self, text: str) -> str:
        """Removes markdown code fences from LLM response text."""
        text = re.sub(r"^```(?:json)?\s*", "", text.strip())
        text = re.sub(r"\s*```$", "", text)
        return text.strip()

    def _call_llm(self, prompt: str, temperature: float) -> dict:
        """Makes a single Gemini API call with retry on JSON parse failure.

        Args:
            prompt: Structured prompt string.
            temperature: Sampling temperature (0.0–1.0).

        Returns:
            dict: Parsed JSON floor plan object.

        Raises:
            RuntimeError: If all retry attempts are exhausted.
        """
        for attempt in range(1, self.max_retries + 1):
            try:
                _logger.info(
                    "LLM call sent: temperature=%.1f, attempt=%d", temperature, attempt
                )
                response = self.model.generate_content(
                    prompt,
                    generation_config=self.genai.GenerationConfig(
                        temperature=temperature,
                        max_output_tokens=2048,
                    ),
                )
                raw = self._strip_fences(response.text)
                parsed = json.loads(raw)
                _logger.info(
                    "LLM call received: temperature=%.1f, attempt=%d — parsed OK",
                    temperature,
                    attempt,
                )
                return parsed

            except json.JSONDecodeError:
                _logger.warning(
                    "JSON parse failed on attempt %d/%d (temperature=%.1f)",
                    attempt,
                    self.max_retries,
                    temperature,
                )
            except Exception as exc:
                _logger.error(
                    "LLM call error on attempt %d/%d: %s", attempt, self.max_retries, exc
                )
                err_str = str(exc)
                if "429" in err_str and attempt < self.max_retries:
                    wait = 60
                    import re as _re
                    m = _re.search(r"retry_delay\s*\{\s*seconds:\s*(\d+)", err_str)
                    if m:
                        wait = int(m.group(1)) + 5
                    _logger.warning("Rate limited — retrying in %ds", wait)
                    time.sleep(wait)
                    continue
                raise RuntimeError(f"LLM call failed: {exc}") from exc

        raise RuntimeError(
            f"LLM generation failed after {self.max_retries} attempts "
            f"(temperature={temperature})"
        )

    def generate(self, prompt: str) -> list[dict]:
        """Makes 3 independent Gemini API calls to produce 3 floor plan alternatives.

        Args:
            prompt: Structured prompt from PromptBuilder.

        Returns:
            list[dict]: 3 floor plan dicts labelled conservative, balanced, creative.
                Each contains the original LLM fields plus temperature and layout_label.
        """
        results: list[dict] = []
        for i, temp in enumerate(self.temperatures):
            result = self._call_llm(prompt, temp)
            result["temperature"] = temp
            result["layout_label"] = _LAYOUT_LABELS[i]
            results.append(result)

        _logger.info("FloorPlanGenerator produced %d alternatives", len(results))
        return results
