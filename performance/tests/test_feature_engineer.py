import pytest

from pipeline.feature_engineer import (
    map_labour_availability,
    map_material_supply,
    map_weather_severity,
    merge_db_context_with_assessment,
)


def test_mapping_values():
    assert map_labour_availability("Very Low") == 0.2
    assert map_material_supply("Yes") == 1
    assert map_weather_severity("Moderate") == 0.6


def test_invalid_mapping_raises():
    with pytest.raises(ValueError):
        map_labour_availability("Bad")


def test_merge_context_builds_expected_fields():
    context = merge_db_context_with_assessment(
        db_context={
            "phase_group": "Foundations",
            "sub_phase": "Foundation work",
            "district": "Colombo",
            "province": "Western Province",
            "floors": 1,
        },
        assessment_payload={
            "delay_category": "Labour",
            "labour_availability": "Low",
            "material_supply": "No",
            "weather_severity": "Minor",
        },
        cumulative_delay=5,
    )
    assert context["labour_availability_score"] == 0.4
    assert context["material_supply_score"] == 0
    assert context["weather_severity_score"] == 0.3
