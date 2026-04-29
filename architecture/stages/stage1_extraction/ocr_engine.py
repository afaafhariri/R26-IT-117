"""
ocr_engine.py — PaddleOCR wrapper for cadastral plan text extraction.

Returns bounding-box-anchored text tokens consumed by NERParser.
"""

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class OCREngine:
    """Extracts text tokens with bounding boxes from a cadastral plan image or PDF page."""

    def __init__(self) -> None:
        # TODO: configure language and GPU flag via environment variables
        self._ocr = self._init_paddle()

    def _init_paddle(self) -> Any:
        """Initialise PaddleOCR with Sri Lankan plan settings (English + Sinhala/Tamil optional)."""
        try:
            from paddleocr import PaddleOCR  # type: ignore

            return PaddleOCR(
                use_angle_cls=True,
                lang="en",
            )
        except ImportError as exc:
            logger.warning("PaddleOCR not available: %s. Using stub.", exc)
            return None

    def extract_text(self, image_path: Path) -> dict:
        """
        Run OCR on a single image and return structured token data.

        Args:
            image_path: Path to the preprocessed image file.

        Returns:
            {
                "tokens": [
                    {
                        "text": str,
                        "confidence": float,
                        "bbox": [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]  # quadrilateral
                    },
                    ...
                ],
                "raw_text": str  # full concatenated text
            }

        Raises:
            FileNotFoundError: If image_path does not exist.
            RuntimeError: If OCR processing fails.
        """
        if not image_path.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")

        try:
            if self._ocr is None:
                return self._stub_result()

            results = self._ocr.ocr(str(image_path), cls=True)
            return self._parse_paddle_results(results)

        except Exception as exc:
            logger.exception("OCR extraction failed for %s", image_path)
            raise RuntimeError(f"OCR failed: {exc}") from exc

    def _parse_paddle_results(self, results: list) -> dict:
        """Convert raw PaddleOCR output to the canonical token schema."""
        tokens = []
        raw_parts: list[str] = []

        for page in results or []:
            for line in page or []:
                bbox, (text, confidence) = line
                tokens.append(
                    {
                        "text": text,
                        "confidence": float(confidence),
                        "bbox": bbox,
                    }
                )
                raw_parts.append(text)

        return {"tokens": tokens, "raw_text": " ".join(raw_parts)}

    def _stub_result(self) -> dict:
        """Return placeholder data when PaddleOCR is unavailable (dev/test mode)."""
        # TODO: replace with real OCR output during integration
        return {
            "tokens": [
                {
                    "text": "PLAN NO: 1234/2023",
                    "confidence": 0.99,
                    "bbox": [[10, 10], [200, 10], [200, 30], [10, 30]],
                },
                {
                    "text": "DISTRICT: COLOMBO",
                    "confidence": 0.97,
                    "bbox": [[10, 40], [200, 40], [200, 60], [10, 60]],
                },
                {
                    "text": "AREA: 720.5 SQ.M",
                    "confidence": 0.95,
                    "bbox": [[10, 70], [200, 70], [200, 90], [10, 90]],
                },
            ],
            "raw_text": "PLAN NO: 1234/2023 DISTRICT: COLOMBO AREA: 720.5 SQ.M",
        }
