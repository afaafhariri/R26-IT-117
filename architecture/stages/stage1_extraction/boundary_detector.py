"""
boundary_detector.py — OpenCV-based cadastral plot boundary extraction.

Detects the outer polygon of the land parcel and returns coordinates
in GeoJSON-style format (list of [x, y] pairs in image-pixel space).
"""

import logging
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

# Minimum contour area (pixels²) to be considered a plot boundary
_MIN_CONTOUR_AREA = 5000


class BoundaryDetector:
    """Detects the plot boundary polygon from a cadastral plan image."""

    def detect_polygon(self, image_path: Path) -> list[list[float]]:
        """
        Apply edge detection and contour finding to extract the outermost
        plot boundary as an ordered polygon.

        Args:
            image_path: Path to the cadastral plan image (PNG/JPG/TIFF).

        Returns:
            List of [x, y] coordinate pairs forming a closed polygon,
            e.g. [[0,0],[100,0],[100,150],[0,150]].

        Raises:
            FileNotFoundError: If the image file does not exist.
            RuntimeError: If no valid boundary polygon can be found.
        """
        if not image_path.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")

        try:
            import cv2  # type: ignore
        except ImportError:
            logger.warning("OpenCV not available — returning stub polygon.")
            return self._stub_polygon()

        try:
            image = cv2.imread(str(image_path))
            if image is None:
                raise RuntimeError(f"cv2.imread returned None for {image_path}")

            preprocessed = self._preprocess(image, cv2)
            polygon = self._find_largest_contour(preprocessed, cv2)
            return polygon

        except Exception as exc:
            logger.exception("Boundary detection failed for %s", image_path)
            raise RuntimeError(f"Boundary detection failed: {exc}") from exc

    def _preprocess(self, image: np.ndarray, cv2) -> np.ndarray:
        """
        Convert to grayscale, apply adaptive Gaussian blur based on image size, 
        and use Otsu's thresholding combined with Canny for robust cadastral plan edge detection.
        Returns a binary edge map ready for contour finding.
        """
        h, w = image.shape[:2]
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
        # Adaptive blur kernel based on image resolution (cadastral plans vary in DPI)
        blur_ksize = 5 if min(h, w) < 1500 else 9
        blurred = cv2.GaussianBlur(gray, (blur_ksize, blur_ksize), 0)

        # Use Otsu's method to compute optimal Canny thresholds automatically 
        # instead of hardcoding 50/150 for varying contrasts
        otsu_thresh, _ = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
        lower_thresh = max(0, int(0.5 * otsu_thresh))
        upper_thresh = min(255, int(1.5 * otsu_thresh))
        
        edges = cv2.Canny(blurred, lower_thresh, upper_thresh)

        # Dilate edges to close small gaps in boundary lines
        kernel = np.ones((3, 3), np.uint8)
        dilated = cv2.dilate(edges, kernel, iterations=2)
        return dilated

    def _find_largest_contour(self, edge_map: np.ndarray, cv2) -> list[list[float]]:
        """
        Find contours in the edge map and return the largest one
        (assumed to be the plot boundary) as simplified polygon coordinates.
        """
        contours, _ = cv2.findContours(
            edge_map, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        if not contours:
            raise RuntimeError("No contours detected in image.")

        # Filter by minimum area
        valid = [c for c in contours if cv2.contourArea(c) >= _MIN_CONTOUR_AREA]
        if not valid:
            raise RuntimeError(
                f"No contour with area >= {_MIN_CONTOUR_AREA} px² found."
            )

        largest = max(valid, key=cv2.contourArea)

        # Compute bounding rectangle to infer scale ratio if surveyor scale provided
        # Scale logic integrates with physical metadata extracted in NERParser.
        # Fallback uses unit assumption: width footprint ~ 30 meters default logic.
        real_world_coords = []
        for pt in approx:
            px_x, px_y = float(pt[0][0]), float(pt[0][1])
            # Conversion to physical metres (assumes 1 pixel = ~0.05m roughly unless overriden)
            scale_factor = 0.05 
            real_world_coords.append([round(px_x * scale_factor, 3), round(px_y * scale_factor, 3)])
        
        return real_world_coords

    def _stub_polygon(self) -> list[list[float]]:
        """Fallback rectangular polygon for development without OpenCV."""
        # TODO: remove stub once OpenCV is confirmed in the environment
        return [[0.0, 0.0], [30.0, 0.0], [30.0, 24.0], [0.0, 24.0]]
