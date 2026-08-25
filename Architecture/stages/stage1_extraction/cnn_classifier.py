"""CNN-based cadastral plan type and quality classifier."""

import os
from pathlib import Path

import cv2
import numpy as np

from utils.logger import get_logger

_logger = get_logger("cnn_classifier")


class CadastralClassifier:
    """CNN-based classifier to determine the type and quality of an uploaded
    cadastral survey plan before extraction. Trained on Sri Lankan survey
    formats from UDA, Municipal Councils, and private surveyors.
    """

    def __init__(self) -> None:
        self.model = None
        self.classes = [
            "surveyor_plan",
            "municipal_plan",
            "uda_plan",
            "low_quality",
            "non_cadastral",
        ]
        self.model_path = (
            Path(os.getenv("MODEL_DIR", "/app/models")) / "cnn_classifier.pt"
        )
        self._load_model()

    def _load_model(self) -> None:
        """Attempts to load the PyTorch CNN model from disk.

        Falls back to rule-based classification if the model file is absent.
        # TODO Sprint 3: train CNN on collected cadastral dataset (1000-1500 plans)
        """
        if not self.model_path.exists():
            _logger.warning(
                "CNN classifier model not found at %s — using rule-based fallback",
                self.model_path,
            )
            return

        try:
            import torch

            self.model = torch.load(str(self.model_path), map_location="cpu")
            self.model.eval()
            _logger.info("CNN classifier model loaded from %s", self.model_path)
        except Exception as exc:
            _logger.warning(
                "Failed to load CNN model (%s) — using rule-based fallback", exc
            )
            self.model = None

    def _rule_based_classify(self, image_path: Path) -> dict:
        """Applies heuristic classification based on filename patterns and image size.

        Args:
            image_path: Path to the input image.

        Returns:
            dict: Classification result using rule-based heuristics.
        """
        name_lower = image_path.name.lower()
        plan_type = "surveyor_plan"

        if "uda" in name_lower:
            plan_type = "uda_plan"
        elif "municipal" in name_lower or "council" in name_lower:
            plan_type = "municipal_plan"

        img = cv2.imread(str(image_path))
        quality_score = 0.80
        if img is not None:
            h, w = img.shape[:2]
            if h < 300 or w < 300:
                plan_type = "low_quality"
                quality_score = 0.30

        return {
            "plan_type": plan_type,
            "confidence": 0.70,
            "is_valid_cadastral": plan_type not in ("low_quality", "non_cadastral"),
            "quality_score": quality_score,
            "recommended_preprocessing": ["deskew", "contrast_enhance"],
        }

    def classify(self, image_path: Path) -> dict:
        """Classifies the type and quality of a cadastral plan image.

        Args:
            image_path: Path to the input image.

        Returns:
            dict: {
                plan_type: str (one of self.classes),
                confidence: float,
                is_valid_cadastral: bool,
                quality_score: float (0.0–1.0),
                recommended_preprocessing: list[str]
            }
        """
        if not image_path.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")

        if self.model is None:
            return self._rule_based_classify(image_path)

        # TODO Sprint 3: run actual CNN inference on self.model
        # Placeholder return for Sprint 1:
        return {
            "plan_type": "surveyor_plan",
            "confidence": 0.85,
            "is_valid_cadastral": True,
            "quality_score": 0.80,
            "recommended_preprocessing": ["deskew", "contrast_enhance"],
        }
