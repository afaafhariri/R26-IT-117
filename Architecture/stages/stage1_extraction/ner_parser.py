"""SpaCy + regex NER parser for Sri Lankan cadastral survey text."""

import re
from typing import Optional

from utils.logger import get_logger

_logger = get_logger("ner_parser")

_COASTAL_DISTRICTS = {
    "Ampara", "Trincomalee", "Batticaloa", "Jaffna", "Kilinochchi",
    "Mannar", "Galle", "Matara", "Hambantota", "Puttalam",
    "Colombo", "Gampaha", "Kalutara",
}

_DISTRICT_NAMES = [
    "Ampara", "Anuradhapura", "Badulla", "Batticaloa", "Colombo",
    "Galle", "Gampaha", "Hambantota", "Jaffna", "Kalutara", "Kandy",
    "Kegalle", "Kilinochchi", "Kurunegala", "Mannar", "Matale",
    "Matara", "Monaragala", "Mullaitivu", "Nuwara Eliya", "Polonnaruwa",
    "Puttalam", "Ratnapura", "Trincomalee", "Vavuniya",
]

_DISTRICT_PATTERN = "|".join(re.escape(d.upper()) for d in _DISTRICT_NAMES)


class NERParser:
    """Extracts structured cadastral fields from OCR text tokens using SpaCy NER
    and domain-specific regular expressions.
    """

    def __init__(self) -> None:
        try:
            import spacy

            self.nlp = spacy.load("en_core_web_sm")
        except OSError as exc:
            _logger.error(
                "SpaCy model 'en_core_web_sm' not found. "
                "Install with: python -m spacy download en_core_web_sm"
            )
            raise RuntimeError(
                "SpaCy model 'en_core_web_sm' not found. "
                "Run: python -m spacy download en_core_web_sm"
            ) from exc

        self.patterns = {
            "plan_number": re.compile(
                r"PLAN\s*(?:No\.?|NO\.?|Number)?\s*(\d+)", re.IGNORECASE
            ),
            "district": re.compile(
                rf"({_DISTRICT_PATTERN})\s*(?:DISTRICT)?", re.IGNORECASE
            ),
            "area": re.compile(
                r"(\d+(?:\.\d+)?)\s*(Hectare|Ha|ha|perch(?:es)?|P\b|sq\.?\s*m(?:etre)?s?)",
                re.IGNORECASE,
            ),
            "scale": re.compile(r"Scale\s*1\s*[:/]\s*(\d+)", re.IGNORECASE),
            "surveyor": re.compile(
                r"(?:Surveyor|Prepared\s+by|Drawn\s+by)[:\s]+([A-Z][a-zA-Z\s\.]{2,40})",
                re.IGNORECASE,
            ),
            "road_access": re.compile(
                r"(National\s+Road|Main\s+Road|Provincial\s+Road|Lane|SLPA\s+Road|Grama)",
                re.IGNORECASE,
            ),
            "lot_number": re.compile(r"Lot\s*(?:No\.?)?\s*(\d+[A-Za-z]?)", re.IGNORECASE),
            # Matches "N 231025", "N=231025.5", "231025 N", "231025N"
            "coordinate_n": re.compile(
                r"(?:N\s*[:=]?\s*(\d+(?:\.\d+)?)|(\d+(?:\.\d+)?)\s*N\b)", re.IGNORECASE
            ),
            "coordinate_e": re.compile(
                r"(?:E\s*[:=]?\s*(\d+(?:\.\d+)?)|(\d+(?:\.\d+)?)\s*E\b)", re.IGNORECASE
            ),
            "licence_number": re.compile(
                r"Lic(?:ence|ense)?\s*(?:No\.?)?\s*([A-Z0-9\-/]+)", re.IGNORECASE
            ),
        }
        _logger.info("NERParser initialised with %d regex patterns", len(self.patterns))

    def _convert_to_sqm(self, value: float, unit: str) -> float:
        """Converts area from perches or hectares to square metres.

        Args:
            value: Numeric area value.
            unit: Unit string extracted from text.

        Returns:
            float: Area in square metres.
        """
        unit_lower = unit.lower().strip()
        if unit_lower in ("p", "perch", "perches"):
            return value * 25.2929
        if unit_lower in ("hectare", "ha"):
            return value * 10000
        return value

    def parse(self, text_tokens: dict) -> dict:
        """Extracts structured cadastral fields from OCR text tokens using NER + regex.

        Args:
            text_tokens: dict from OCREngine.extract_text() containing raw_text.

        Returns:
            dict: {
                plan_number: str | None,
                district: str | None,
                area_sqm: float | None,
                scale: int | None,
                surveyor: str | None,
                road_access: str | None,
                lot_number: str | None,
                is_coastal: bool,
                province: str | None,
                coordinate_n: float | None,
                coordinate_e: float | None,
                licence_number: str | None
            }
        """
        text: str = text_tokens.get("raw_text", "")
        _logger.info("NER parsing started (%d chars)", len(text))

        result: dict = {
            "plan_number": None,
            "district": None,
            "area_sqm": None,
            "scale": None,
            "surveyor": None,
            "road_access": None,
            "lot_number": None,
            "is_coastal": False,
            "province": None,
            "coordinate_n": None,
            "coordinate_e": None,
            "licence_number": None,
        }

        m = self.patterns["plan_number"].search(text)
        if m:
            result["plan_number"] = m.group(1)

        m = self.patterns["district"].search(text)
        if m:
            matched = m.group(1).title()
            for d in _DISTRICT_NAMES:
                if d.upper() == matched.upper():
                    result["district"] = d
                    break

        m = self.patterns["area"].search(text)
        if m:
            value = float(m.group(1))
            unit = m.group(2)
            result["area_sqm"] = round(self._convert_to_sqm(value, unit), 4)

        m = self.patterns["scale"].search(text)
        if m:
            result["scale"] = int(m.group(1))

        m = self.patterns["surveyor"].search(text)
        if m:
            result["surveyor"] = m.group(1).strip()

        m = self.patterns["road_access"].search(text)
        if m:
            result["road_access"] = m.group(1).strip()

        m = self.patterns["lot_number"].search(text)
        if m:
            result["lot_number"] = m.group(1)

        m = self.patterns["coordinate_n"].search(text)
        if m:
            result["coordinate_n"] = float(m.group(1) or m.group(2))

        m = self.patterns["coordinate_e"].search(text)
        if m:
            result["coordinate_e"] = float(m.group(1) or m.group(2))

        m = self.patterns["licence_number"].search(text)
        if m:
            result["licence_number"] = m.group(1)

        doc = self.nlp(text[:5000])
        for ent in doc.ents:
            if ent.label_ == "PERSON" and result["surveyor"] is None:
                result["surveyor"] = ent.text
            elif ent.label_ == "GPE" and result["province"] is None:
                result["province"] = ent.text

        if result["district"] and result["district"] in _COASTAL_DISTRICTS:
            result["is_coastal"] = True

        _logger.info(
            "NER parsing complete — district=%s, area_sqm=%s, is_coastal=%s",
            result["district"],
            result["area_sqm"],
            result["is_coastal"],
        )
        # TODO Sprint 4: fine-tune SpaCy NER on annotated Sri Lankan cadastral corpus
        return result
