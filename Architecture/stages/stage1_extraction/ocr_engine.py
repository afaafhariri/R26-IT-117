"""EasyOCR-based text extraction for cadastral survey images.

EasyOCR uses PyTorch and is compatible with numpy 2.x on Windows,
unlike PaddleOCR which has PIR/OneDNN compatibility issues on Python 3.13.
"""

from pathlib import Path

from utils.logger import get_logger

_logger = get_logger("ocr_engine")


class OCREngine:
    """Extracts bounding-box-anchored text tokens from cadastral scan images
    using EasyOCR (PyTorch-based, numpy 2.x compatible).
    """

    def __init__(self) -> None:
        import easyocr

        _logger.info("Initialising EasyOCR engine (lang=en)")
        # gpu=False forces CPU inference; detail=1 returns bbox+text+confidence
        self._reader = easyocr.Reader(["en"], gpu=False, verbose=False)
        _logger.info("EasyOCR engine ready")

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
            from PIL import Image
            import numpy as np

            pil_img = Image.open(image_path).convert("RGB")
            width, height = pil_img.size
            img_array = np.array(pil_img)

            # EasyOCR result: list of (bbox, text, confidence)
            # bbox is [[x1,y1],[x2,y1],[x2,y2],[x1,y2]]
            raw = self._reader.readtext(img_array, detail=1, paragraph=False)

            tokens: list[dict] = []
            for bbox, text, confidence in raw:
                tokens.append(
                    {
                        "text": text,
                        "bbox": [list(pt) for pt in bbox],
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
                "_image_path": str(image_path),
            }

        except (FileNotFoundError, RuntimeError):
            raise
        except Exception as exc:
            _logger.error("OCR engine error on %s: %s", image_path, exc)
            raise RuntimeError(f"OCR engine failed for {image_path}: {exc}") from exc
