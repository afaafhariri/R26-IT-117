"""OpenCV-based land boundary polygon detector for cadastral survey images."""

from pathlib import Path

import cv2
import numpy as np

from utils.logger import get_logger

_logger = get_logger("boundary_detector")


class BoundaryDetector:
    """Detects the land boundary polygon from cadastral survey scan images."""

    # Plot polygon must occupy between 5% and 70% of the image area.
    # Below 5% → tiny annotation; above 70% → page border, not the plot.
    _MIN_AREA_FRAC = 0.05
    _MAX_AREA_FRAC = 0.70

    # Typical Sri Lankan cadastral plots have 4–14 corner vertices.
    _MIN_VERTICES = 4
    _MAX_VERTICES = 14

    # Solidity = contour area / convex hull area.
    # Plot shapes are mostly convex — reject very concave blobs (text clusters).
    _MIN_SOLIDITY = 0.55

    def __init__(self) -> None:
        _logger.info("BoundaryDetector initialised")

    def _preprocess(self, image: np.ndarray) -> np.ndarray:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        # Mild blur — removes scan noise without smearing the boundary lines
        return cv2.GaussianBlur(gray, (3, 3), 0)

    def _candidates_from_binary(
        self, binary: np.ndarray, total_area: int
    ) -> list[tuple[float, np.ndarray]]:
        """Return (area, approx_polygon) pairs for all plausible plot contours."""

        # Morphological close: bridges small gaps between line segment endpoints
        # so that the plot outline forms a single closed contour.
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        closed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=2)

        # RETR_LIST — retrieve all contours regardless of hierarchy so we are
        # not limited to the outermost shape (which is the page border).
        contours, _ = cv2.findContours(
            closed, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE
        )

        candidates = []
        for c in contours:
            area = cv2.contourArea(c)

            # Reject page border (too large) and tiny annotations (too small)
            if not (total_area * self._MIN_AREA_FRAC < area < total_area * self._MAX_AREA_FRAC):
                continue

            peri = cv2.arcLength(c, closed=True)
            approx = cv2.approxPolyDP(c, 0.02 * peri, closed=True)
            n_verts = len(approx)

            if not (self._MIN_VERTICES <= n_verts <= self._MAX_VERTICES):
                continue

            hull_area = cv2.contourArea(cv2.convexHull(c))
            solidity = area / hull_area if hull_area > 0 else 0
            if solidity < self._MIN_SOLIDITY:
                continue

            candidates.append((area, approx))

        # Largest valid candidate is most likely the plot polygon
        return sorted(candidates, key=lambda x: x[0], reverse=True)

    def detect_polygon(self, image_path: Path) -> list:
        """Detect the land boundary polygon from a cadastral survey image.

        Returns:
            list: [[x1,y1],[x2,y2],...] with coordinates normalised to [0,1]
                  relative to image dimensions.

        Falls back to a centred rectangle if no valid contour is found.
        """
        image_path = Path(image_path)
        if not image_path.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")

        _logger.info("Boundary detection started: %s", image_path)

        img = cv2.imread(str(image_path))
        if img is None:
            raise ValueError(f"Could not read image: {image_path}")

        height, width = img.shape[:2]
        total_area = height * width
        processed = self._preprocess(img)

        # --- Pass 1: Otsu global threshold (works well on clean scans) ---
        _, binary_otsu = cv2.threshold(
            processed, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
        )
        candidates = self._candidates_from_binary(binary_otsu, total_area)

        if candidates:
            area, best = candidates[0]
            polygon = [[float(pt[0][0]) / width, float(pt[0][1]) / height]
                       for pt in best]
            _logger.info(
                "Boundary detected (Otsu): %d vertices, area=%.1f px² (%d candidates)",
                len(polygon), area, len(candidates),
            )
            return polygon

        # --- Pass 2: Adaptive threshold (handles uneven lighting / shadows) ---
        binary_adaptive = cv2.adaptiveThreshold(
            processed, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 15, 4,
        )
        candidates = self._candidates_from_binary(binary_adaptive, total_area)

        if candidates:
            area, best = candidates[0]
            polygon = [[float(pt[0][0]) / width, float(pt[0][1]) / height]
                       for pt in best]
            _logger.info(
                "Boundary detected (adaptive): %d vertices, area=%.1f px²",
                len(polygon), area,
            )
            return polygon

        # --- Fallback: centred rectangle at 60% of image ---
        _logger.warning(
            "No valid boundary contour found in %s — using centred fallback rectangle",
            image_path,
        )
        px, py = 0.20, 0.15
        return [
            [px,       py],
            [1 - px,   py],
            [1 - px,   1 - py],
            [px,       1 - py],
        ]
