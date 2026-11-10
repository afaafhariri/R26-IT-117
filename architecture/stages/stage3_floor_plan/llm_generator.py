"""Gemini API client for multi-temperature floor plan generation."""

import json
import os
import re
import time

from utils.logger import get_logger

_logger = get_logger("llm_generator")

_LAYOUT_LABELS = ["conservative", "balanced", "creative"]

_VARIANT_DIRECTIVES = {
    "conservative": (
        "VARIANT: CONSERVATIVE — Prioritise COMPACTNESS and EFFICIENCY. "
        "Minimise circulation space. Pack rooms tightly in a grid. "
        "Use the smallest reasonable room sizes while meeting targets. "
        "Straight corridors, rectangular rooms, no wasted space."
    ),
    "balanced": (
        "VARIANT: BALANCED — Create a WELL-PROPORTIONED layout with generous room sizes. "
        "Living and dining areas should be large and open. "
        "Bedrooms should be comfortable with space for wardrobes. "
        "Good cross-ventilation. Vary room sizes — don't make all rooms the same dimensions."
    ),
    "creative": (
        "VARIANT: CREATIVE — Design an INNOVATIVE, OPEN-PLAN layout. "
        "Merge living and dining into one large open zone. Use non-standard room proportions — "
        "some rooms very wide, others deep. Large master suite. "
        "Break away from the grid — use the full floor depth for key rooms."
    ),
}


class FloorPlanGenerator:
    """Generates 3 floor plan alternatives using Gemini at different temperatures
    to produce a conservative, balanced, and creative option.
    """

    def __init__(self) -> None:
        from google.genai import types
        from utils.gemini_client import get_client

        self.client = get_client()
        self.types = types
        self.model_name = os.getenv("GEMINI_FLOOR_PLAN_MODEL", "gemini-2.5-flash")
        self.temperatures = [0.4, 0.7, 1.0]
        self.max_retries = 3
        _logger.info("FloorPlanGenerator initialised (model=%s)", self.model_name)

    def _extract_json(self, text: str) -> dict:
        """Robustly extracts the floor plan JSON object from LLM response text.

        Scans for every top-level { } object using json.JSONDecoder.raw_decode
        (which respects string boundaries). Returns the first candidate that
        has a "rooms" list — i.e. the floor plan, not a room sub-object.
        """
        text = re.sub(r"^```(?:json)?\s*", "", text.strip())
        text = re.sub(r"\s*```$", "", text).strip()

        decoder = json.JSONDecoder()
        candidates: list[dict] = []
        for i, ch in enumerate(text):
            if ch == '{':
                try:
                    obj, _ = decoder.raw_decode(text, i)
                    if isinstance(obj, dict):
                        candidates.append(obj)
                except json.JSONDecodeError:
                    continue

        # Prefer the candidate that looks like a full floor plan
        for obj in candidates:
            if "rooms" in obj and isinstance(obj["rooms"], list) and obj["rooms"]:
                return obj

        # Fallback: any candidate with a rooms key (even empty)
        for obj in candidates:
            if "rooms" in obj:
                return obj

        if candidates:
            return candidates[0]

        raise json.JSONDecodeError("No valid floor plan JSON found in response", text, 0)

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
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                    config=self.types.GenerateContentConfig(
                        temperature=temperature,
                        max_output_tokens=8192,
                        response_mime_type="application/json",
                        thinking_config=self.types.ThinkingConfig(thinking_level="minimal"),
                    ),
                )
                raw = response.text or ""
                _logger.info(
                    "LLM raw response length=%d, first 400 chars: %s",
                    len(raw), raw[:400],
                )
                parsed = self._extract_json(raw)
                _logger.info(
                    "LLM call received: temperature=%.1f, attempt=%d — parsed OK",
                    temperature,
                    attempt,
                )
                return parsed

            except json.JSONDecodeError as jex:
                _logger.warning(
                    "JSON parse failed on attempt %d/%d (temperature=%.1f) at pos %d — raw: %s",
                    attempt,
                    self.max_retries,
                    temperature,
                    jex.pos,
                    raw[:600],
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
            label = _LAYOUT_LABELS[i]
            directive = _VARIANT_DIRECTIVES[label]
            # Prepend variant directive so each call gets a meaningfully different prompt
            variant_prompt = f"{directive}\n\n{prompt}"
            result = self._call_llm(variant_prompt, temp)
            result["temperature"] = temp
            result["layout_label"] = label
            results.append(result)

        _logger.info("FloorPlanGenerator produced %d alternatives", len(results))
        return results
