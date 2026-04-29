"""
Unit tests for the normalisation, feature engineering, and delay-prediction pipeline.

Run with::

    pytest tests/test_pipeline.py -v
"""

import math
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from ingestion.progress_normaliser import ProgressNormaliser
from pipeline.feature_engineer import FeatureEngineer
from pipeline.preprocessor import Preprocessor
from pipeline.delay_model import DelayPredictor


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def make_raw_record(
    project_id: str = "proj-001",
    planned_pct: float = 50.0,
    actual_pct: float = 45.0,
    phase: str = "foundation",
    labour_count: int = 20,
    material_deliveries: int = 3,
    weather_delay_days: int = 0,
    rework_incidents: int = 1,
    timestamp: datetime | None = None,
) -> dict:
    return {
        "project_id": project_id,
        "timestamp": timestamp or datetime.now(timezone.utc),
        "phase": phase,
        "planned_completion_pct": planned_pct,
        "actual_completion_pct": actual_pct,
        "labour_count": labour_count,
        "material_deliveries": material_deliveries,
        "weather_delay_days": weather_delay_days,
        "rework_incidents": rework_incidents,
    }


@pytest.fixture()
def normaliser():
    return ProgressNormaliser()


@pytest.fixture()
def sample_records():
    return [make_raw_record(planned_pct=p, actual_pct=a)
            for p, a in [(10, 9), (20, 17), (30, 24), (40, 31), (50, 40)]]


@pytest.fixture()
def normalised_records(normaliser, sample_records):
    return [normaliser.normalise(r) for r in sample_records]


# ---------------------------------------------------------------------------
# ProgressNormaliser tests
# ---------------------------------------------------------------------------

class TestProgressNormaliser:

    def test_basic_normalisation(self, normaliser):
        raw = make_raw_record(planned_pct=50.0, actual_pct=45.0)
        result = normaliser.normalise(raw)

        assert result["schedule_variance"] == pytest.approx(-5.0, abs=0.01)
        assert result["schedule_performance_index"] == pytest.approx(0.9, abs=0.001)
        assert result["is_delayed"] is True
        assert result["days_behind"] > 0

    def test_on_schedule(self, normaliser):
        raw = make_raw_record(planned_pct=60.0, actual_pct=60.0)
        result = normaliser.normalise(raw)

        assert result["schedule_variance"] == pytest.approx(0.0, abs=0.001)
        assert result["schedule_performance_index"] == pytest.approx(1.0, abs=0.001)
        assert result["is_delayed"] is False
        assert result["days_behind"] == 0

    def test_ahead_of_schedule(self, normaliser):
        raw = make_raw_record(planned_pct=40.0, actual_pct=50.0)
        result = normaliser.normalise(raw)

        assert result["schedule_variance"] == pytest.approx(10.0, abs=0.01)
        assert result["schedule_performance_index"] > 1.0
        assert result["is_delayed"] is False
        assert result["days_behind"] == 0

    def test_spi_zero_planned(self, normaliser):
        """SPI should be 1.0 (on-schedule) at project start when planned == 0."""
        raw = make_raw_record(planned_pct=0.0, actual_pct=0.0)
        result = normaliser.normalise(raw)
        assert result["schedule_performance_index"] == pytest.approx(1.0)

    def test_spi_clamped_at_max(self, normaliser):
        """SPI should not exceed SPI_CLAMP_MAX (2.0)."""
        raw = make_raw_record(planned_pct=10.0, actual_pct=100.0)
        result = normaliser.normalise(raw)
        assert result["schedule_performance_index"] <= 2.0

    def test_timestamp_becomes_utc(self, normaliser):
        raw = make_raw_record()
        raw["timestamp"] = "2025-06-01T09:00:00"
        result = normaliser.normalise(raw)
        assert result["timestamp"].tzinfo is not None

    def test_missing_required_field_raises(self, normaliser):
        raw = {"actual_completion_pct": 50.0}
        with pytest.raises(ValueError, match="missing required fields"):
            normaliser.normalise(raw)

    def test_invalid_percentage_raises(self, normaliser):
        raw = make_raw_record()
        raw["actual_completion_pct"] = 150.0
        with pytest.raises(ValueError, match="must be in \\[0, 100\\]"):
            normaliser.normalise(raw)


# ---------------------------------------------------------------------------
# Preprocessor tests
# ---------------------------------------------------------------------------

class TestPreprocessor:

    def test_fit_transform_returns_dataframe(self, normalised_records):
        preprocessor = Preprocessor()
        df = preprocessor.fit_transform(normalised_records)
        assert isinstance(df, pd.DataFrame)
        assert len(df) == len(normalised_records)

    def test_scaled_columns_present(self, normalised_records):
        preprocessor = Preprocessor()
        df = preprocessor.fit_transform(normalised_records)
        assert "schedule_performance_index_scaled" in df.columns

    def test_phase_encoded_column_present(self, normalised_records):
        preprocessor = Preprocessor()
        df = preprocessor.fit_transform(normalised_records)
        assert "phase_encoded" in df.columns

    def test_transform_before_fit_raises(self, normalised_records):
        preprocessor = Preprocessor()
        with pytest.raises(RuntimeError, match="fitted"):
            preprocessor.transform(normalised_records)

    def test_empty_input_returns_empty_df(self):
        preprocessor = Preprocessor()
        df = preprocessor.fit_transform([])
        assert df.empty

    def test_missing_values_imputed(self, normaliser):
        records = [normaliser.normalise(make_raw_record()) for _ in range(5)]
        records[2]["labour_count"] = None   # inject missing value
        preprocessor = Preprocessor()
        df = preprocessor.fit_transform(records)
        assert not df["labour_count"].isna().any()


# ---------------------------------------------------------------------------
# FeatureEngineer tests
# ---------------------------------------------------------------------------

class TestFeatureEngineer:

    BUILDING_SCHEMA = {
        "floors": 12,
        "footprint_sqm": 2500.0,
        "structural_complexity_score": 1.8,
    }

    COST_REPORT = {
        "total_labour_days": 450,
        "overall_budget_consumed_pct": 35.0,
    }

    def test_build_features_returns_dataframe(self, normalised_records):
        preprocessor = Preprocessor()
        df = preprocessor.fit_transform(normalised_records)
        fe = FeatureEngineer()
        features = fe.build_features(df, self.BUILDING_SCHEMA, self.COST_REPORT)
        assert isinstance(features, pd.DataFrame)
        assert not features.empty

    def test_site_features_broadcast(self, normalised_records):
        preprocessor = Preprocessor()
        df = preprocessor.fit_transform(normalised_records)
        fe = FeatureEngineer()
        features = fe.build_features(df, self.BUILDING_SCHEMA, self.COST_REPORT)

        assert (features["floors"] == 12).all()
        assert (features["footprint_sqm"] == 2500.0).all()

    def test_rolling_progress_rate_column_present(self, normalised_records):
        preprocessor = Preprocessor()
        df = preprocessor.fit_transform(normalised_records)
        fe = FeatureEngineer()
        features = fe.build_features(df, self.BUILDING_SCHEMA, self.COST_REPORT)
        assert "rolling_7day_progress_rate" in features.columns

    def test_rework_rate_computed(self, normalised_records):
        preprocessor = Preprocessor()
        df = preprocessor.fit_transform(normalised_records)
        fe = FeatureEngineer()
        features = fe.build_features(df, self.BUILDING_SCHEMA, self.COST_REPORT)
        assert "rework_rate_per_100_labour_days" in features.columns
        assert (features["rework_rate_per_100_labour_days"] >= 0).all()

    def test_empty_df_returns_empty(self):
        fe = FeatureEngineer()
        result = fe.build_features(pd.DataFrame(), {}, {})
        assert result.empty


# ---------------------------------------------------------------------------
# DelayPredictor tests
# ---------------------------------------------------------------------------

class TestDelayPredictor:

    def _build_features(self, normalised_records):
        preprocessor = Preprocessor()
        df = preprocessor.fit_transform(normalised_records)
        fe = FeatureEngineer()
        return fe.build_features(
            df,
            {"floors": 5, "footprint_sqm": 1000.0, "structural_complexity_score": 1.0},
            {"total_labour_days": 200, "overall_budget_consumed_pct": 20.0},
        )

    def test_predict_returns_required_keys(self, normalised_records):
        features = self._build_features(normalised_records)
        predictor = DelayPredictor()
        result = predictor.predict(features)

        assert "delay_risk" in result
        assert "predicted_delay_days" in result
        assert "confidence" in result
        assert "primary_cause" in result

    def test_delay_risk_valid_value(self, normalised_records):
        features = self._build_features(normalised_records)
        predictor = DelayPredictor()
        result = predictor.predict(features)
        assert result["delay_risk"] in ("low", "medium", "high")

    def test_predicted_days_non_negative(self, normalised_records):
        features = self._build_features(normalised_records)
        predictor = DelayPredictor()
        result = predictor.predict(features)
        assert result["predicted_delay_days"] >= 0

    def test_confidence_between_0_and_1(self, normalised_records):
        features = self._build_features(normalised_records)
        predictor = DelayPredictor()
        result = predictor.predict(features)
        assert 0.0 <= result["confidence"] <= 1.0

    def test_empty_features_returns_defaults(self):
        predictor = DelayPredictor()
        result = predictor.predict(pd.DataFrame())
        assert result["delay_risk"] == "low"
        assert result["predicted_delay_days"] == 0
