"""PaddleOCR-based text extraction for cadastral survey images."""

from pathlib import Path

import cv2
import numpy as np

from utils.logger import get_logger

_logger = get_logger("ocr_engine")


class OCREngine:
    """Extracts bounding-box-anchored text tokens from cadastral scan images
    using PaddleOCR.
    """

    def __init__(self) -> None:
        from paddleocr import PaddleOCR

        _logger.info("Initialising PaddleOCR engine")
        self.ocr = PaddleOCR(lang="en", use_angle_cls=True, use_gpu=False)
        _logger.info("PaddleOCR engine ready")

    def extract_text(self, image_path: Path) -> dict:
        """Extracts bounding-box-anchored text tokens from a cadastral scan image.

        Args:
            image_path: Path to preprocessed image file (PNG/JPEG).

        Returns:
            dict: {
                tokens: list of {text: str, bbox: [[x,y],...], confidence: float},
                raw_text: str,
                page_dimensions: {width: int, height: int}
            }

        Raises:
            FileNotFoundError: If image_path does not exist.
            RuntimeError: If the OCR engine fails to process the image.
        """
        if not image_path.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")

        _logger.info("OCR started: %s", image_path)

        try:
            img = cv2.imread(str(image_path))
            if img is None:
                raise RuntimeError(f"cv2 could not read image: {image_path}")

            height, width = img.shape[:2]
            result = self.ocr.ocr(str(image_path), cls=True)

            tokens: list[dict] = []
            for page in result or []:
                for line in page or []:
                    bbox, (text, confidence) = line
                    # TODO: add confidence threshold filtering (min 0.6) in Sprint 3
                    tokens.append(
                        {
                            "text": text,
                            "bbox": bbox,
                            "confidence": float(confidence),
                        }
                    )

            raw_text = " ".join(t["text"] for t in tokens)
            _logger.info(
                "OCR complete: %s — %d tokens extracted", image_path, len(tokens)
            )
            return {
                "tokens": tokens,
                "raw_text": raw_text,
                "page_dimensions": {"width": width, "height": height},
            }

        except (FileNotFoundError, RuntimeError):
            raise
        except Exception as exc:
            _logger.error("OCR engine error on %s: %s", image_path, exc)
            raise RuntimeError(f"OCR engine failed for {image_path}: {exc}") from exc
