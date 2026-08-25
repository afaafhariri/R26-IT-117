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

# Words that are NOT surveyor names — strip from end of surveyor match
_SURVEYOR_STRIP = re.compile(
    r"\b(Sri\s+Lanka|Survey\s+Department|Licensed|Registered|Surveyor|General|"
    r"Department|Land|Commission|Survey|Authority|UDA|SLAS)\b.*",
    re.IGNORECASE,
)
_SURVEYOR_BLOCKLIST = {
    "sri lanka", "survey department", "land", "general",
    "department", "surveyor", "licensed surveyor", "registered",
    "registered licensed", "licensed",
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
        import spacy
        from pathlib import Path

        # Try fine-tuned cadastral model first, fall back to base model
        _fine_tuned = Path(__file__).resolve().parents[3] / "models" / "ner_cadastral"
        try:
            if _fine_tuned.exists():
                self.nlp = spacy.load(str(_fine_tuned))
                self._has_fine_tuned = True
                _logger.info("Loaded fine-tuned cadastral NER model from %s", _fine_tuned)
            else:
                self.nlp = spacy.load("en_core_web_sm")
                self._has_fine_tuned = False
                _logger.info("Fine-tuned model not found — using en_core_web_sm")
        except OSError as exc:
            _logger.error(
                "SpaCy model not found. Run: python -m spacy download en_core_web_sm"
            )
            raise RuntimeError("SpaCy model not found.") from exc

        self.patterns = {
            "plan_number": re.compile(
                r"PLAN\s*(?:No\.?|NO\.?|Number)?\s*(\d+)", re.IGNORECASE
            ),
            "district": re.compile(
                rf"({_DISTRICT_PATTERN})\s*(?:DISTRICT)?", re.IGNORECASE
            ),
            "area": re.compile(
                r"(?:extent|area|containing)[^0-9]{0,30}(\d+(?:\.\d+)?)\s*(Square\s+metre|Hectare|Ha|ha|perch(?:es)?|sq\.?\s*m(?:etre)?s?)"
                r"|=\s*(\d+(?:\.\d+)?)\s*(Square\s+metre|sq\.?\s*m(?:etre)?s?)",
                re.IGNORECASE,
            ),
            "scale": re.compile(r"Scale\s*1\s*[:/]\s*(\d+)", re.IGNORECASE),
            # SL plans: "S.M.Ibrahim (CSSI Sri Lanka)" — name before (CSSI
            # OR name before (Chartered Surveyor)
            # OR name before "Licensed/Registered Licensed Surveyor" (direct)
            # OR name after "Prepared/Drawn by"
            "surveyor": re.compile(
                r"([A-Z][A-Za-z\.]{1,20}(?:\s+[A-Z][A-Za-z\.]{1,20}){0,3})\s*\(\s*CSSI"
                r"|([A-Z][A-Za-z\.]{1,20}(?:\s+[A-Z][A-Za-z\.]{1,20}){0,3})\s*\(\s*Chartered\s+Surveyor"
                r"|([A-Z][A-Za-z\.]{1,30}(?:\s+[A-Z][A-Za-z\.]{1,30}){1,4})\s+(?:Registered\s+)?Licensed\s+Surveyor"
                r"|(?:Prepared\s+by|Drawn\s+by)[:\s]+([A-Z][a-zA-Z\s\.]{2,40})",
                re.IGNORECASE,
            ),
            "road_access": re.compile(
                r"(National\s+Road|Main\s+Road|Provincial\s+Road|Lane|SLPA\s+Road|Grama)",
                re.IGNORECASE,
            ),
            # \d+ also handles OCR misread of "1" as "I" via post-processing
            "lot_number": re.compile(
                r"(?:Lot|Plot|Parcel)\s*(?:No\.?|Number)?\s*([0-9IiOo]+[A-Za-z]?)"
                r"|(?:^|\s)([0-9IiOo]+[A-Za-z]?)\s*(?:Lot|Plot)\b",
                re.IGNORECASE | re.MULTILINE,
            ),
            # Matches "N 231025", "N=231025.5", "231025 N", "231025N", "N: 231025"
            "coordinate_n": re.compile(
                r"(?<![A-Z])N\s*[:=]?\s*(\d{6,}(?:\.\d+)?)"
                r"|(\d{6,}(?:\.\d+)?)\s*N(?![A-Z])",
                re.IGNORECASE,
            ),
            # Matches "E 319950", "E=319950.5", "319950 E", "319950E", "E: 319950"
            "coordinate_e": re.compile(
                r"(?<![A-Z])E\s*[:=]?\s*(\d{6,}(?:\.\d+)?)"
                r"|(\d{6,}(?:\.\d+)?)\s*E(?![A-Z])",
                re.IGNORECASE,
            ),
            # Require "No" after Lic to avoid matching "Licensed" → captures "d"
            "licence_number": re.compile(
                r"Lic(?:ence|ense)?\s*No\.?\s*([A-Z0-9][A-Z0-9\-/]{2,})", re.IGNORECASE
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
        if "square" in unit_lower or unit_lower.startswith("sq"):
            return value  # already in sqm
        return value

    def _extract_rotated_coordinate_e(self, text_tokens: dict, n_val: float) -> float | None:
        """Crops right and left margin strips, rotates 90°, and OCRs for E coordinate.

        SLD99 E coordinates on Sri Lankan cadastral plans are often printed
        vertically (rotated 90°) along the right or left edge. EasyOCR cannot
        read rotated text in normal mode, so we extract a margin strip,
        rotate it upright, then re-run OCR.
        Tries both CCW (90) and CW (-90) rotations to handle either text orientation.
        """
        try:
            import easyocr
            import numpy as np
            from PIL import Image, ImageFilter, ImageEnhance

            img_path = text_tokens.get("_image_path")
            if not img_path:
                return None

            img = Image.open(img_path).convert("RGB")
            w, h = img.size
            strip_width = max(80, int(w * 0.09))

            reader = easyocr.Reader(["en"], gpu=False, verbose=False)
            e_pattern = re.compile(r"\b(\d{6}(?:\.\d+)?)\b")

            def _enhance(strip: Image.Image) -> np.ndarray:
                gray = strip.convert("L")
                gray = ImageEnhance.Contrast(gray).enhance(2.0)
                gray = gray.filter(ImageFilter.SHARPEN)
                return np.array(gray.convert("RGB"))

            strips = [
                img.crop((w - strip_width, 0, w, h)),
                img.crop((0, 0, strip_width, h)),
            ]
            for strip in strips:
                # Try both rotation directions — text may be written top-to-bottom or bottom-to-top
                for angle in (90, -90):
                    rotated = strip.rotate(angle, expand=True)
                    arr = _enhance(rotated)
                    results = reader.readtext(arr, detail=0, paragraph=False)
                    strip_text = " ".join(results)
                    _logger.info("Rotated strip OCR (angle=%d): %s", angle, strip_text[:200])
                    for m in e_pattern.finditer(strip_text):
                        val = float(m.group(1))
                        if 200_000 <= val <= 700_000 and abs(val - n_val) > 20_000:
                            _logger.info("coordinate_e from rotated strip (angle=%d): %s", angle, val)
                            return val
        except Exception as exc:
            _logger.warning("Rotated E extraction failed: %s", exc)
        return None

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
        _logger.info("NER raw_text (first 1200): %s", text[:1200])

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
            # Groups 1,2 = extent/area context match; groups 3,4 = =X sqm match
            value = float(m.group(1) or m.group(3))
            unit  = m.group(2) or m.group(4)
            result["area_sqm"] = round(self._convert_to_sqm(value, unit), 4)

        m = self.patterns["scale"].search(text)
        if m:
            result["scale"] = int(m.group(1))

        m = self.patterns["surveyor"].search(text)
        if m:
            # Groups: 1=before CSSI, 2=before Chartered, 3=before Licensed, 4=after Prepared/Drawn by
            raw_name = (m.group(1) or m.group(2) or m.group(3) or m.group(4) or "").strip()
            # Strip trailing non-name words (e.g. "Sri Lanka Survey Department")
            cleaned = _SURVEYOR_STRIP.sub("", raw_name).strip().rstrip(".,;")
            if cleaned and cleaned.lower() not in _SURVEYOR_BLOCKLIST and len(cleaned) > 2:
                result["surveyor"] = cleaned
            else:
                _logger.warning("Surveyor name rejected (blocklist/empty): %r → %r", raw_name, cleaned)

        m = self.patterns["road_access"].search(text)
        if m:
            result["road_access"] = m.group(1).strip()

        m = self.patterns["lot_number"].search(text)
        if m:
            raw_lot = (m.group(1) or m.group(2) or "").strip()
            corrected = raw_lot.replace("I", "1").replace("O", "0").replace("i", "1").replace("o", "0")
            result["lot_number"] = corrected

        # Fallback: OCR often drops the digit from "Lot 1" in italic description text.
        # Find standalone digit token in the center region of the plan (the lot label).
        if result["lot_number"] is None:
            tokens = text_tokens.get("tokens", [])
            dims = text_tokens.get("page_dimensions", {})
            w = dims.get("width", 1190)
            h = dims.get("height", 1684)
            for tok in tokens:
                tok_text = tok["text"].strip()
                if re.match(r"^\d{1,3}[A-Za-z]?$", tok_text):
                    bbox = tok["bbox"]
                    cx = (bbox[0][0] + bbox[2][0]) / 2
                    cy = (bbox[0][1] + bbox[2][1]) / 2
                    # Lot label sits in the centre of the plot (35–75% width, 15–65% height)
                    if 0.35 * w <= cx <= 0.75 * w and 0.15 * h <= cy <= 0.65 * h:
                        result["lot_number"] = tok_text
                        _logger.info("lot_number from centre token: %s at (%.0f,%.0f)", tok_text, cx, cy)
                        break

        # Last-resort fallback: OCR drops the digit from italic "Lot 1 situated" text.
        # If "marked as Lot" (or similar) appears without a following digit, it is
        # almost always a single-lot plan — default to "1".
        if result["lot_number"] is None:
            if re.search(r"marked\s+as\s+Lot\s*(?:situated|at\b|in\b|,)", text, re.IGNORECASE):
                result["lot_number"] = "1"
                _logger.info("lot_number defaulted to '1' (OCR dropped digit after 'marked as Lot')")

        # SLD99 Northings are 100000–600000, Eastings are 200000–700000.
        # Reject small values (e.g. "077" from phone numbers like "077 6550260").
        for match in self.patterns["coordinate_n"].finditer(text):
            val = float(match.group(1) or match.group(2))
            if 100_000 <= val <= 600_000:
                result["coordinate_n"] = val
                break

        for match in self.patterns["coordinate_e"].finditer(text):
            val = float(match.group(1) or match.group(2))
            if 200_000 <= val <= 700_000:
                result["coordinate_e"] = val
                break

        # Fallback for rotated E coordinate — EasyOCR cannot read 90° rotated text.
        # Crop the right margin strip, rotate 90° CCW, then OCR that strip.
        if result["coordinate_e"] is None:
            result["coordinate_e"] = self._extract_rotated_coordinate_e(
                text_tokens, result.get("coordinate_n") or 0
            )

        m = self.patterns["licence_number"].search(text)
        if m:
            result["licence_number"] = m.group(1)

        doc = self.nlp(text[:5000])
        for ent in doc.ents:
            if self._has_fine_tuned:
                # Fine-tuned model: use cadastral labels to fill regex gaps
                if ent.label_ == "DISTRICT" and result["district"] is None:
                    matched = ent.text.strip().title()
                    for d in _DISTRICT_NAMES:
                        if d.upper() == matched.upper():
                            result["district"] = d
                            break
                elif ent.label_ == "PLAN_NO" and result["plan_number"] is None:
                    result["plan_number"] = ent.text.strip()
                elif ent.label_ == "SURVEYOR" and result["surveyor"] is None:
                    result["surveyor"] = ent.text.strip()
                elif ent.label_ == "LOT_NO" and result["lot_number"] is None:
                    result["lot_number"] = ent.text.strip()
                elif ent.label_ == "LICENCE" and result["licence_number"] is None:
                    result["licence_number"] = ent.text.strip()
            else:
                # Base model: use generic labels
                if ent.label_ == "PERSON" and result["surveyor"] is None:
                    candidate = ent.text.strip()
                    cleaned = _SURVEYOR_STRIP.sub("", candidate).strip().rstrip(".,;")
                    if cleaned and cleaned.lower() not in _SURVEYOR_BLOCKLIST and len(cleaned) > 2:
                        result["surveyor"] = cleaned
                    else:
                        _logger.warning("spaCy PERSON rejected (blocklist): %r", candidate)
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
        return result
