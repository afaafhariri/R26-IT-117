import pytest

from pipeline.delay_model import predict


def _valid_payload():
    return {
        "phase_group": "Foundations",
        "sub_phase": "Foundation work",
        "district": "Colombo",
        "province": "Western Province",
        "floors": 1,
        "delay_category": "Labour",
        "labour_availability": 0.6,
        "material_supply": 1,
        "weather_severity": 0.4,
        "cumulative_delay": 10,
    }


def test_prediction_returns_risk_label():
    result = predict(**_valid_payload())
    assert result["risk_level"] in {"HIGH", "MEDIUM", "LOW"}


def test_prediction_returns_delay_days_not_negative():
    result = predict(**_valid_payload())
    assert result["delay_days"] >= 0


def test_error_on_unknown_category():
    payload = _valid_payload()
    payload["delay_category"] = "UNKNOWN_CATEGORY"
    with pytest.raises(ValueError):
        predict(**payload)


def test_error_when_required_context_missing():
    payload = _valid_payload()
    payload["phase_group"] = None
    with pytest.raises(ValueError):
        predict(**payload)
