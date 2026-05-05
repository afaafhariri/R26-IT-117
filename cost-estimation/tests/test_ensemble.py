"""Tests for Layer 3: feature engineering, XGBoost model, and ensemble."""

import numpy as np
import pandas as pd
import pytest

from layers.layer3_ml_prediction.feature_engineer import FeatureEngineer
from layers.layer3_ml_prediction.xgboost_model import XGBoostCostModel
from layers.layer3_ml_prediction.ensemble import EnsembleCostPredictor
from layers.layer3_ml_prediction.shap_explainer import SHAPExplainer


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_boq(sample_building_schema):
    from layers.layer1_boq.boq_engine import BOQEngine
    return BOQEngine().run(sample_building_schema)


@pytest.fixture
def feature_df(sample_boq, sample_building_schema):
    fe = FeatureEngineer()
    return fe.build_features(sample_boq, sample_building_schema, "mid")


@pytest.fixture
def trained_xgb_model(feature_df):
    """XGBoost model trained on synthetic data."""
    model = XGBoostCostModel()
    rng = np.random.default_rng(42)
    X = pd.concat([feature_df] * 50, ignore_index=True)
    X += rng.normal(0, 0.1, X.shape)
    y = pd.Series(rng.lognormal(mean=15, sigma=0.5, size=len(X)))
    model.train(X, y)
    return model


# ---------------------------------------------------------------------------
# FeatureEngineer
# ---------------------------------------------------------------------------

class TestFeatureEngineer:
    def test_returns_dataframe(self, sample_boq, sample_building_schema):
        fe = FeatureEngineer()
        df = fe.build_features(sample_boq, sample_building_schema, "mid")
        assert isinstance(df, pd.DataFrame)

    def test_single_row_output(self, feature_df):
        assert len(feature_df) == 1

    def test_all_required_features_present(self, feature_df):
        expected = FeatureEngineer.feature_names()
        for col in expected:
            assert col in feature_df.columns, f"Missing feature: {col}"

    def test_no_nans_or_infs(self, feature_df):
        assert not feature_df.isnull().any().any()
        assert not np.isinf(feature_df.values).any()

    def test_district_multiplier_colombo_is_1(self, sample_boq, sample_building_schema):
        fe = FeatureEngineer()
        df = fe.build_features(sample_boq, sample_building_schema, "mid")
        assert df["district_multiplier"].iloc[0] == pytest.approx(1.00)

    def test_finish_grade_economy_encodes_0(self, sample_boq, sample_building_schema):
        fe = FeatureEngineer()
        df = fe.build_features(sample_boq, sample_building_schema, "economy")
        assert df["finish_grade_encoded"].iloc[0] == 0

    def test_finish_grade_luxury_encodes_2(self, sample_boq, sample_building_schema):
        fe = FeatureEngineer()
        df = fe.build_features(sample_boq, sample_building_schema, "luxury")
        assert df["finish_grade_encoded"].iloc[0] == 2

    def test_coastal_flag_encoded_as_int(self, sample_boq, sample_building_schema):
        fe = FeatureEngineer()
        df = fe.build_features(sample_boq, sample_building_schema, "mid")
        assert df["is_coastal"].iloc[0] in (0, 1)


# ---------------------------------------------------------------------------
# XGBoostCostModel
# ---------------------------------------------------------------------------

class TestXGBoostCostModel:
    def test_predict_returns_positive_after_training(self, trained_xgb_model, feature_df):
        prediction = trained_xgb_model.predict(feature_df)
        assert isinstance(prediction, float)
        assert prediction > 0

    def test_predict_interval_lower_lt_upper(self, trained_xgb_model, feature_df):
        lower, upper = trained_xgb_model.predict_interval(feature_df)
        assert lower < upper

    def test_predict_returns_zero_when_not_loaded(self, feature_df):
        model = XGBoostCostModel()
        assert model.predict(feature_df) == 0.0

    def test_interval_returns_zeros_when_not_loaded(self, feature_df):
        model = XGBoostCostModel()
        lower, upper = model.predict_interval(feature_df)
        assert lower == 0.0 and upper == 0.0

    def test_is_loaded_true_after_training(self, trained_xgb_model):
        assert trained_xgb_model.is_loaded is True

    def test_save_and_load_roundtrip(self, trained_xgb_model, feature_df, tmp_path):
        pred_before = trained_xgb_model.predict(feature_df)
        trained_xgb_model.save(str(tmp_path))
        model2 = XGBoostCostModel()
        model2.load(str(tmp_path))
        pred_after = model2.predict(feature_df)
        assert pred_before == pytest.approx(pred_after, rel=1e-4)


# ---------------------------------------------------------------------------
# EnsembleCostPredictor
# ---------------------------------------------------------------------------

class TestEnsembleCostPredictor:
    def test_predict_returns_required_keys(self, feature_df):
        ensemble = EnsembleCostPredictor(auto_load=False)
        result = ensemble.predict(feature_df)
        required = {
            "point_estimate_lkr", "lower_bound_lkr", "upper_bound_lkr",
            "xgboost_prediction", "mlp_prediction", "confidence_level",
        }
        assert required.issubset(result.keys())

    def test_confidence_level_is_0_90(self, feature_df):
        ensemble = EnsembleCostPredictor(auto_load=False)
        result = ensemble.predict(feature_df)
        assert result["confidence_level"] == 0.90

    def test_no_models_returns_zeros(self, feature_df):
        ensemble = EnsembleCostPredictor(auto_load=False)
        result = ensemble.predict(feature_df)
        assert result["point_estimate_lkr"] == 0.0

    def test_with_xgb_loaded_uses_xgb(self, trained_xgb_model, feature_df):
        ensemble = EnsembleCostPredictor(xgboost_model=trained_xgb_model, auto_load=False)
        result = ensemble.predict(feature_df)
        assert result["point_estimate_lkr"] == pytest.approx(result["xgboost_prediction"], rel=1e-6)

    def test_lower_bound_lte_point_estimate(self, trained_xgb_model, feature_df):
        ensemble = EnsembleCostPredictor(xgboost_model=trained_xgb_model, auto_load=False)
        result = ensemble.predict(feature_df)
        if result["lower_bound_lkr"] > 0:
            assert result["lower_bound_lkr"] <= result["point_estimate_lkr"]


# ---------------------------------------------------------------------------
# SHAPExplainer
# ---------------------------------------------------------------------------

class TestSHAPExplainer:
    def test_explain_returns_list_with_loaded_model(self, trained_xgb_model, feature_df):
        explainer = SHAPExplainer(top_n=5)
        result = explainer.explain(trained_xgb_model, feature_df)
        assert isinstance(result, list)

    def test_each_entry_has_required_keys(self, trained_xgb_model, feature_df):
        explainer = SHAPExplainer(top_n=5)
        result = explainer.explain(trained_xgb_model, feature_df)
        for item in result:
            assert "feature" in item
            assert "impact_lkr" in item
            assert "direction" in item

    def test_direction_values_are_valid(self, trained_xgb_model, feature_df):
        explainer = SHAPExplainer(top_n=5)
        result = explainer.explain(trained_xgb_model, feature_df)
        for item in result:
            assert item["direction"] in ("increases", "decreases")

    def test_returns_empty_list_without_model(self, feature_df):
        explainer = SHAPExplainer()
        result = explainer.explain(XGBoostCostModel(), feature_df)
        assert result == []

    def test_format_summary_non_empty(self, trained_xgb_model, feature_df):
        explainer = SHAPExplainer(top_n=3)
        explanations = explainer.explain(trained_xgb_model, feature_df)
        summary = explainer.format_summary(explanations)
        assert isinstance(summary, str)
        assert len(summary) > 0
