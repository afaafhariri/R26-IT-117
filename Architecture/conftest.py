"""Root conftest — adds Architecture/ to sys.path and pre-mocks ML packages
that can't be imported cleanly under Python 3.13 (numpy 2.x ABI mismatch).
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))

# paddleocr 2.7.3 and opencv were compiled against numpy 1.x; numpy 2.x
# (installed by paddlepaddle 3.3.1) has an incompatible ABI.  Pre-stub both
# modules with realistic return values so tests work without the real binaries.

# -- paddleocr stub ----------------------------------------------------------
if "paddleocr" not in sys.modules:
    sys.modules["paddleocr"] = MagicMock()

# -- cv2 stub ----------------------------------------------------------------
if "cv2" not in sys.modules:
    _h, _w = 500, 500
    _dummy_bgr  = np.ones((_h, _w, 3), dtype=np.uint8) * 200
    _dummy_gray = np.ones((_h, _w),    dtype=np.uint8) * 200
    _dummy_bin  = np.zeros((_h, _w),   dtype=np.uint8)

    # A rectangular contour that covers 80 % of the image (plausible plot boundary)
    _dummy_contour = np.array(
        [[[50, 50]], [[450, 50]], [[450, 450]], [[50, 450]]], dtype=np.int32
    )

    _cv2 = MagicMock()
    _cv2.imread.return_value          = _dummy_bgr
    _cv2.cvtColor.return_value        = _dummy_gray
    _cv2.GaussianBlur.return_value    = _dummy_gray
    _cv2.Canny.return_value           = _dummy_bin
    _cv2.threshold.return_value       = (128, _dummy_bin)
    _cv2.findContours.return_value    = ([_dummy_contour], None)
    _cv2.contourArea.return_value     = 160000.0   # 400 × 400 px²
    _cv2.arcLength.return_value       = 1600.0
    _cv2.approxPolyDP.return_value    = _dummy_contour

    # Common integer constants
    _cv2.COLOR_BGR2GRAY              = 6
    _cv2.COLOR_BGR2RGB               = 4
    _cv2.IMREAD_GRAYSCALE            = 0
    _cv2.RETR_EXTERNAL               = 0
    _cv2.CHAIN_APPROX_SIMPLE         = 2
    _cv2.THRESH_BINARY               = 0
    _cv2.THRESH_BINARY_INV           = 1
    _cv2.THRESH_OTSU                 = 8

    sys.modules["cv2"] = _cv2
