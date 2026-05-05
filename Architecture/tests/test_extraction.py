"""Tests for Stage 1 extraction pipeline."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PIL import Image


def _write_png(path: Path, arr: np.ndarray) -> None:
    """Write a numpy array as PNG using Pillow (cv2 is stubbed in conftest)."""
    Image.fromarray(arr.astype(np.uint8)).save(str(path))


# ---------------------------------------------------------------------------
# OCREngine
# ---------------------------------------------------------------------------

class TestOCREngine:
    def test_ocr_engine_raises_on_missing_file(self):
        """OCREngine must raise FileNotFoundError for a non-existent path."""
        # PaddleOCR is imported lazily inside __init__; patch at source location.
        with patch("paddleocr.PaddleOCR"):
            from stages.stage1_extraction.ocr_engine import OCREngine

            engine = OCREngine.__new__(OCREngine)
            engine.ocr = MagicMock()

        with pytest.raises(FileNotFoundError):
            engine.extract_text(Path("/tmp/nonexistent_image_xyz.png"))

    def test_ocr_engine_returns_tokens(self, tmp_path):
        """extract_text must return a dict with tokens, raw_text, page_dimensions."""
        img_path = tmp_path / "test.png"
        img = np.ones((10, 10, 3), dtype=np.uint8) * 255
        _write_png(img_path, img)

        # EasyOCR returns list of (bbox, text, confidence)
        mock_ocr_result = [
            ([[10, 10], [50, 10], [50, 30], [10, 30]], "PLAN No. 2362", 0.98),
        ]

        from stages.stage1_extraction.ocr_engine import OCREngine

        engine = OCREngine.__new__(OCREngine)
        mock_reader = MagicMock()
        mock_reader.readtext.return_value = mock_ocr_result
        engine._reader = mock_reader

        result = engine.extract_text(img_path)

        assert "tokens" in result
        assert "raw_text" in result
        assert "page_dimensions" in result
        assert isinstance(result["tokens"], list)
        assert len(result["tokens"]) == 1
        assert result["tokens"][0]["text"] == "PLAN No. 2362"


# ---------------------------------------------------------------------------
# CNNClassifier
# ---------------------------------------------------------------------------

class TestCadastralClassifier:
    def test_cnn_classifier_returns_valid_structure(self, tmp_path):
        """classify must return all required keys regardless of model state."""
        img_path = tmp_path / "plan.png"
        img = np.ones((100, 100, 3), dtype=np.uint8) * 200
        _write_png(img_path, img)

        from stages.stage1_extraction.cnn_classifier import CadastralClassifier

        classifier = CadastralClassifier.__new__(CadastralClassifier)
        classifier.model = None
        classifier.classes = [
            "surveyor_plan", "municipal_plan", "uda_plan",
            "low_quality", "non_cadastral",
        ]
        classifier.model_path = Path("/nonexistent/model.pt")

        result = classifier.classify(img_path)

        required_keys = {
            "plan_type", "confidence", "is_valid_cadastral",
            "quality_score", "recommended_preprocessing",
        }
        assert required_keys.issubset(result.keys())
        assert result["plan_type"] in classifier.classes
        assert 0.0 <= result["confidence"] <= 1.0
        assert isinstance(result["is_valid_cadastral"], bool)
        assert 0.0 <= result["quality_score"] <= 1.0
        assert isinstance(result["recommended_preprocessing"], list)


# ---------------------------------------------------------------------------
# BoundaryDetector
# ---------------------------------------------------------------------------

class TestBoundaryDetector:
    def test_boundary_detector_returns_polygon(self, tmp_path):
        """detect_polygon must return a list of normalised [x, y] pairs."""
        img_path = tmp_path / "cadastral.png"
        img = np.zeros((500, 500, 3), dtype=np.uint8)
        # Draw a white rectangle border to simulate a cadastral boundary
        img[50:453, 50:53] = 255   # left edge
        img[50:453, 450:453] = 255  # right edge
        img[50:53, 50:453] = 255   # top edge
        img[450:453, 50:453] = 255  # bottom edge
        _write_png(img_path, img)

        from stages.stage1_extraction.boundary_detector import BoundaryDetector

        polygon = BoundaryDetector().detect_polygon(img_path)

        assert isinstance(polygon, list)
        assert len(polygon) >= 3
        for point in polygon:
            assert len(point) == 2
            assert 0.0 <= point[0] <= 1.0
            assert 0.0 <= point[1] <= 1.0

    def test_boundary_detector_raises_on_missing_file(self):
        """detect_polygon must raise FileNotFoundError for a non-existent path."""
        from stages.stage1_extraction.boundary_detector import BoundaryDetector

        with pytest.raises(FileNotFoundError):
            BoundaryDetector().detect_polygon(Path("/tmp/no_such_file_xyz.png"))


# ---------------------------------------------------------------------------
# NERParser
# ---------------------------------------------------------------------------

class TestNERParser:
    def _make_parser(self):
        """Returns a NERParser instance with a mocked SpaCy model."""
        mock_doc = MagicMock()
        mock_doc.ents = []
        with patch("spacy.load", return_value=MagicMock(return_value=mock_doc)):
            from stages.stage1_extraction.ner_parser import NERParser
            return NERParser()

    def test_ner_parser_extracts_district(self):
        """parse must identify 'Ampara' from text containing 'AMPARA DISTRICT'."""
        parser = self._make_parser()
        tokens = {"raw_text": "PLAN No. 2362  AMPARA DISTRICT  Area: 472.9 Perches"}
        result = parser.parse(tokens)
        assert result["district"] == "Ampara"

    def test_ner_parser_coastal_flag(self):
        """Ampara → is_coastal True; Kandy → is_coastal False."""
        parser = self._make_parser()
        coastal = parser.parse({"raw_text": "AMPARA DISTRICT Area 200 Perches"})
        inland = parser.parse({"raw_text": "KANDY DISTRICT Area 200 Perches"})
        assert coastal["is_coastal"] is True
        assert inland["is_coastal"] is False


# ---------------------------------------------------------------------------
# SchemaAssembler
# ---------------------------------------------------------------------------

class TestSchemaAssembler:
    def test_schema_assembler_validates_output(self, sample_site_schema):
        """assemble must return a dict with all required top-level keys."""
        from stages.stage1_extraction.schema_assembler import SchemaAssembler

        assembler = SchemaAssembler.__new__(SchemaAssembler)
        assembler.schema = None  # skip jsonschema validation in unit test

        ocr_result = {
            "tokens": [],
            "raw_text": "PLAN No. 2362 AMPARA DISTRICT 472.9 Perches",
            "page_dimensions": {"width": 2480, "height": 3508},
        }
        polygon = [[0.05, 0.05], [0.85, 0.05], [0.85, 0.90], [0.05, 0.90]]
        ner_result = {
            "plan_number": "2362",
            "district": "Ampara",
            "area_sqm": 472.9,
            "scale": 500,
            "surveyor": "S.M. Perera",
            "road_access": "Provincial Road",
            "lot_number": "7A",
            "is_coastal": True,
            "province": "Eastern",
            "coordinate_n": 7.298,
            "coordinate_e": 81.687,
            "licence_number": "SL/SURV/2021/1145",
        }

        result = assembler.assemble(ocr_result, polygon, ner_result)

        for key in ("plan_id", "district", "area_sqm", "boundary_polygon", "is_coastal"):
            assert key in result
        assert result["district"] == "Ampara"
        assert result["is_coastal"] is True
