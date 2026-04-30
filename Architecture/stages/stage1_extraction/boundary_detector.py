"""OpenCV-based land boundary polygon detector for cadastral survey images."""

from pathlib import Path

import cv2
import numpy as np

from utils.logger import get_logger

_logger = get_logger("boundary_detector")


class BoundaryDetector:
    """Detects the land boundary polygon from cadastral survey scan images
    using edge detection and contour analysis.
    """

    def __init__(self) -> None:
        _logger.info("BoundaryDetector initialised")
        self.min_contour_area = 5000  # pixels squared, configurable

    def _preprocess(self, image: np.ndarray) -> np.ndarray:
        """Preprocesses image for boundary detection.

        Applies grayscale conversion, CLAHE contrast normalisation, and
        Gaussian blur to reduce noise before edge detection.

        Args:
            image: BGR image array from cv2.imread.

        Returns:
            np.ndarray: Preprocessed single-channel image.
        """
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)
        blurred = cv2.GaussianBlur(enhanced, (5, 5), 0)
        # TODO Sprint 2: add deskew using Hough transform
        return blurred

    def detect_polygon(self, image_path: Path) -> list:
        """Detects the land boundary polygon from a cadastral survey image.

        Args:
            image_path: Path to the image file.

        Returns:
            list: GeoJSON-style coordinate array [[x1,y1],[x2,y2],...] where
                each coordinate is normalised to 0.0–1.0 relative to image
                dimensions.

        Raises:
            FileNotFoundError: If image_path does not exist.
            ValueError: If no valid boundary contour is found.
        """
        if not image_path.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")

        _logger.info("Boundary detection started: %s", image_path)

        img = cv2.imread(str(image_path))
        if img is None:
            raise ValueError(f"Could not read image: {image_path}")

        height, width = img.shape[:2]
        processed = self._preprocess(img)

        _, binary = cv2.threshold(processed, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        edges = cv2.Canny(binary, 50, 150)

        contours, _ = cv2.findContours(
            edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        valid = [c for c in contours if cv2.contourArea(c) > self.min_contour_area]
        if not valid:
            raise ValueError(
                f"No valid boundary contour found in {image_path} "
                f"(min area threshold: {self.min_contour_area}px²)"
            )

        largest = max(valid, key=cv2.contourArea)
        perimeter = cv2.arcLength(largest, closed=True)
        approx = cv2.approxPolyDP(largest, epsilon=0.02 * perimeter, closed=True)

        polygon = [
            [float(pt[0][0]) / width, float(pt[0][1]) / height]
            for pt in approx
        ]

        _logger.info(
            "Boundary detection complete: %s — %d vertices", image_path, len(polygon)
        )
        # TODO Sprint 3: add neural network-based boundary segmentation
        return polygon
