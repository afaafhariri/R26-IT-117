"""Load xgboost before any test module pulls in torch or faiss.

On macOS all three link an OpenMP runtime named libomp.dylib, and xgboost
segfaults when another library's copy was loaded first (see
pipeline/delay_model.py).
"""

import xgboost  # noqa: F401
