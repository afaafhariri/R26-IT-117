"""
ner_parser.py — SpaCy-based Named Entity Recognition for cadastral legal text.

Extracts structured fields from OCR token output:
  plan_number, district, area_sqm, scale, surveyor, road_access, lot_number
"""

import re
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Regex patterns for fields not reliably caught by NER alone
_PLAN_NUMBER_RE = re.compile(r"PLAN\s*(?:NO[:\.]?|NUMBER[:\.]?)\s*([A-Z0-9/\-]+)", re.I)
_AREA_RE = re.compile(r"AREA[:\s]+([0-9]+(?:\.[0-9]+)?)\s*(?:SQ\.?\s*M|M2|SQM)", re.I)
_SCALE_RE = re.compile(r"SCALE\s*1\s*[:/]\s*([0-9]+)", re.I)
_LOT_RE = re.compile(r"LOT\s*(?:NO[:\.]?)?\s*([A-Z0-9/\-]+)", re.I)


class NERParser:
    """
    Parses cadastral OCR tokens with SpaCy NER and regex fallbacks
    to extract canonical site metadata.
    """

    def __init__(self) -> None:
        self._nlp = self._load_model()

    def _load_model(self) -> Any:
        """Load SpaCy model; falls back gracefully when unavailable."""
        try:
            import spacy  # type: ignore

            return spacy.load("en_core_web_sm")
        except (ImportError, OSError) as exc:
            logger.warning("SpaCy model unavailable: %s. Using regex-only mode.", exc)
            return None

    def parse(self, ocr_result: dict) -> dict:
        """
        Extract structured metadata fields from OCR token output.

        Args:
            ocr_result: Output from OCREngine.extract_text(), containing
                        keys 'tokens' (list) and 'raw_text' (str).

        Returns:
            {
                "plan_number": str | None,
                "district":    str | None,
                "area_sqm":    float | None,
                "scale":       str | None,   # e.g. "1:500"
                "surveyor":    str | None,
                "road_access": str | None,
                "lot_number":  str | None,
            }

        Raises:
            ValueError: If ocr_result does not contain 'raw_text'.
        """
        if "raw_text" not in ocr_result:
            raise ValueError("ocr_result must contain 'raw_text' key.")

        raw_text: str = ocr_result["raw_text"]
        result: dict[str, Any] = {
            "plan_number": None,
            "district": None,
            "area_sqm": None,
            "scale": None,
            "surveyor": None,
            "road_access": None,
            "lot_number": None,
        }

        # ── Regex extraction ──────────────────────────────────────────────
        result["plan_number"] = self._match(_PLAN_NUMBER_RE, raw_text)
        result["lot_number"] = self._match(_LOT_RE, raw_text)
        result["scale"] = self._extract_scale(raw_text)

        area_str = self._match(_AREA_RE, raw_text)
        if area_str:
            try:
                result["area_sqm"] = float(area_str)
            except ValueError:
                pass

        # ── SpaCy NER extraction ──────────────────────────────────────────
        if self._nlp is not None:
            result.update(self._ner_extract(raw_text, result))
        else:
            # TODO: extend regex fallbacks for district, surveyor, road_access
            result.update(self._regex_fallback(raw_text))

        return result

    def _ner_extract(self, text: str, current: dict) -> dict:
        """Use SpaCy entities to fill district, surveyor, and road_access."""
        doc = self._nlp(text)
        updates: dict[str, Any] = {}

        # Sri Lankan districts are typically GPE (geo-political entities) in spaCy
        for ent in doc.ents:
            if ent.label_ == "GPE" and current["district"] is None:
                updates["district"] = ent.text.title()
            if ent.label_ == "PERSON" and current["surveyor"] is None:
                updates["surveyor"] = ent.text.title()

        # TODO: fine-tune spaCy with cadastral plan corpus for higher accuracy
        updates["road_access"] = self._infer_road_access(text)

        return updates

    def _regex_fallback(self, text: str) -> dict:
        """Minimal regex extraction when SpaCy is unavailable."""
        district_re = re.compile(
            r"DISTRICT[:\s]+([A-Z][A-Z\s]+?)(?:\s+PLAN|\s+LOT|\s+AREA|$)", re.I
        )
        return {
            "district": self._match(district_re, text),
            "road_access": self._infer_road_access(text),
        }

    @staticmethod
    def _match(pattern: re.Pattern, text: str) -> str | None:
        """Return the first capturing group match or None."""
        m = pattern.search(text)
        return m.group(1).strip() if m else None

    @staticmethod
    def _extract_scale(text: str) -> str | None:
        m = _SCALE_RE.search(text)
        return f"1:{m.group(1)}" if m else None

    @staticmethod
    def _infer_road_access(text: str) -> str | None:
        """
        Heuristically detect road access description from cadastral text.
        TODO: replace with a trained classifier for Sri Lankan road typology.
        """
        text_lower = text.lower()
        if "national" in text_lower or "a-grade" in text_lower:
            return "national_road"
        if "provincial" in text_lower or "b-grade" in text_lower:
            return "provincial"
        if "lane" in text_lower or "private road" in text_lower:
            return "lane"
        if "road" in text_lower or "street" in text_lower:
            return "local"
        return None
