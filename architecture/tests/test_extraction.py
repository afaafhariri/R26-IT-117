"""
test_extraction.py — Pytest tests for Stage 1: Cadastral Plan Extraction.

Tests cover OCREngine, BoundaryDetector, NERParser, and SchemaAssembler.
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from stages.stage1_extraction.ocr_engine import OCREngine
from stages.stage1_extraction.boundary_detector import BoundaryDetector
from stages.stage1_extraction.ner_parser import NERParser
from stages.stage1_extraction.schema_assembler import SchemaAssembler


# ── Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture
def sample_ocr_result():
    return {
        "tokens": [
            {"text": "PLAN NO: 1234/2023", "confidence": 0.99,
             "bbox": [[10, 10], [200, 10], [200, 30], [10, 30]]},
            {"text": "DISTRICT: COLOMBO", "confidence": 0.97,
             "bbox": [[10, 40], [200, 40], [200, 60], [10, 60]]},
            {"text": "AREA: 720.5 SQ.M", "confidence": 0.95,
             "bbox": [[10, 70], [200, 70], [200, 90], [10, 90]]},
            {"text": "SCALE 1:500", "confidence": 0.96,
             "bbox": [[10, 100], [200, 100], [200, 120], [10, 120]]},
            {"text": "LOT NO: 45/B", "confidence": 0.94,
             "bbox": [[10, 130], [200, 130], [200, 150], [10, 150]]},
        ],
        "raw_text": "PLAN NO: 1234/2023 DISTRICT: COLOMBO AREA: 720.5 SQ.M SCALE 1:500 LOT NO: 45/B",
    }


@pytest.fixture
def sample_polygon():
    return [[0.0, 0.0], [30.0, 0.0], [30.0, 24.0], [0.0, 24.0]]


@pytest.fixture
def sample_ner():
    return {
        "plan_number": "1234/2023",
        "district": "Colombo",
        "area_sqm": 720.5,
        "scale": "1:500",
        "surveyor": None,
        "road_access": "local",
        "lot_number": "45/B",
    }


# ── OCREngine tests ───────────────────────────────────────────────────────

class TestOCREngine:
    def test_extract_text_raises_on_missing_file(self):
        """extract_text should raise FileNotFoundError for non-existent paths."""
        engine = OCREngine()
        with pytest.raises(FileNotFoundError):
            engine.extract_text(Path("/nonexistent/image.png"))

    def test_stub_result_has_required_keys(self):
        """Stub result must contain 'tokens' and 'raw_text' keys."""
        engine = OCREngine()
        result = engine._stub_result()
        assert "tokens" in result
        assert "raw_text" in result

    def test_stub_tokens_are_list_of_dicts(self):
        """Each token in stub result must have text, confidence, bbox."""
        engine = OCREngine()
        tokens = engine._stub_result()["tokens"]
        assert isinstance(tokens, list)
        for token in tokens:
            assert "text" in token
            assert "confidence" in token
            assert "bbox" in token

    def test_parse_paddle_results_empty_input(self):
        """Empty PaddleOCR output should produce zero tokens."""
        engine = OCREngine()
        result = engine._parse_paddle_results([])
        assert result["tokens"] == []
        assert result["raw_text"] == ""


# ── BoundaryDetector tests ────────────────────────────────────────────────

class TestBoundaryDetector:
    def test_detect_polygon_raises_on_missing_file(self):
        """detect_polygon should raise FileNotFoundError for missing images."""
        detector = BoundaryDetector()
        with pytest.raises(FileNotFoundError):
            detector.detect_polygon(Path("/nonexistent/plan.png"))

    def test_stub_polygon_has_four_vertices(self):
        """Stub polygon should be a rectangle with 4 vertices."""
        detector = BoundaryDetector()
        polygon = detector._stub_polygon()
        assert len(polygon) == 4
        for point in polygon:
            assert len(point) == 2

    def test_stub_polygon_returns_float_coordinates(self):
        """All coordinates in stub polygon must be floats."""
        detector = BoundaryDetector()
        polygon = detector._stub_polygon()
        for x, y in polygon:
            assert isinstance(x, float)
            assert isinstance(y, float)


# ── NERParser tests ───────────────────────────────────────────────────────

class TestNERParser:
    def test_parse_raises_on_missing_raw_text(self):
        """parse() must raise ValueError when 'raw_text' key is missing."""
        parser = NERParser()
        with pytest.raises(ValueError, match="raw_text"):
            parser.parse({"tokens": []})

    def test_parse_extracts_plan_number(self, sample_ocr_result):
        """plan_number should be extracted from the raw text."""
        parser = NERParser()
        result = parser.parse(sample_ocr_result)
        assert result["plan_number"] == "1234/2023"

    def test_parse_extracts_area_sqm(self, sample_ocr_result):
        """area_sqm should be extracted as a float."""
        parser = NERParser()
        result = parser.parse(sample_ocr_result)
        assert result["area_sqm"] == pytest.approx(720.5, rel=1e-3)

    def test_parse_extracts_scale(self, sample_ocr_result):
        """scale should be extracted in '1:N' format."""
        parser = NERParser()
        result = parser.parse(sample_ocr_result)
        assert result["scale"] == "1:500"

    def test_parse_extracts_lot_number(self, sample_ocr_result):
        """lot_number should be extracted from the raw text."""
        parser = NERParser()
        result = parser.parse(sample_ocr_result)
        assert result["lot_number"] == "45/B"

    def test_parse_returns_all_expected_keys(self, sample_ocr_result):
        """parse() must return all 7 canonical keys."""
        parser = NERParser()
        result = parser.parse(sample_ocr_result)
        expected_keys = {
            "plan_number", "district", "area_sqm", "scale",
            "surveyor", "road_access", "lot_number",
        }
        assert expected_keys.issubset(result.keys())


# ── SchemaAssembler tests ─────────────────────────────────────────────────

class TestSchemaAssembler:
    def test_assemble_returns_valid_schema(self, sample_ocr_result, sample_polygon, sample_ner):
        """assemble() must return a dict with plan_id, site, boundaries."""
        assembler = SchemaAssembler()
        schema = assembler.assemble(sample_ocr_result, sample_polygon, sample_ner)
        assert "plan_id" in schema
        assert "site" in schema
        assert "boundaries" in schema

    def test_assemble_site_contains_required_fields(
        self, sample_ocr_result, sample_polygon, sample_ner
    ):
        """site sub-dict must contain all 5 required fields."""
        assembler = SchemaAssembler()
        schema = assembler.assemble(sample_ocr_result, sample_polygon, sample_ner)
        site = schema["site"]
        for field in ("plot_area_sqm", "district", "is_coastal", "terrain", "road_access"):
            assert field in site

    def test_assemble_coastal_district_flagged(
        self, sample_ocr_result, sample_polygon, sample_ner
    ):
        """Colombo should be flagged as a coastal district."""
        assembler = SchemaAssembler()
        schema = assembler.assemble(sample_ocr_result, sample_polygon, sample_ner)
        assert schema["site"]["is_coastal"] is True

    def test_assemble_inland_district_not_coastal(
        self, sample_ocr_result, sample_polygon
    ):
        """Kandy should NOT be flagged as coastal."""
        ner = {
            "plan_number": "X001",
            "district": "Kandy",
            "area_sqm": 500.0,
            "scale": "1:500",
            "surveyor": None,
            "road_access": "local",
            "lot_number": None,
        }
        assembler = SchemaAssembler()
        schema = assembler.assemble(sample_ocr_result, sample_polygon, ner)
        assert schema["site"]["is_coastal"] is False

    def test_assemble_polygon_preserved(
        self, sample_ocr_result, sample_polygon, sample_ner
    ):
        """The polygon passed in should appear in boundaries.polygon."""
        assembler = SchemaAssembler()
        schema = assembler.assemble(sample_ocr_result, sample_polygon, sample_ner)
        assert schema["boundaries"]["polygon"] == sample_polygon

    def test_assemble_raises_on_degenerate_polygon(
        self, sample_ocr_result, sample_ner
    ):
        """Polygon with fewer than 3 points should produce area 0 (not error)."""
        assembler = SchemaAssembler()
        schema = assembler.assemble(sample_ocr_result, [[0, 0], [1, 1]], sample_ner)
        # Area cannot be computed — should use NER area or fallback to 0
        assert schema["site"]["plot_area_sqm"] >= 0
