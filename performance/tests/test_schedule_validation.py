"""
Tests for the POST /schedule non-dict `project` fix in main.py.

NOTE: unlike the rest of this test suite, this module imports `main`
directly, which requires a reachable database (main.py calls init_db() at
import time). This is only expected to pass when run against the full
running stack (e.g. `docker exec r26_performance python -m pytest tests/`
with docker compose up), not as a pure offline unit test.
"""

from main import _validate_schedule_payload

_VALID_PHASE = {
    "phase_group": "Foundations",
    "sub_phase": "Foundation work",
    "planned_start": "2026-01-01",
    "planned_end": "2026-01-10",
    "planned_duration_days": 9,
    "sequence": 1,
}


def test_string_project_returns_clean_validation_error_not_a_crash():
    data = {"project": "not-an-object", "phases": [_VALID_PHASE]}
    errors = _validate_schedule_payload(data)
    assert any("project must be an object" in e for e in errors)
    # Degrades into normal required-field errors instead of crashing.
    assert any("project.name is required" in e for e in errors)


def test_list_project_returns_clean_validation_error_not_a_crash():
    data = {"project": ["a", "b"], "phases": [_VALID_PHASE]}
    errors = _validate_schedule_payload(data)
    assert any("project must be an object" in e for e in errors)


def test_integer_project_returns_clean_validation_error_not_a_crash():
    data = {"project": 5, "phases": [_VALID_PHASE]}
    errors = _validate_schedule_payload(data)
    assert any("project must be an object" in e for e in errors)


def _valid_project(**overrides):
    project = {
        "name": "Test Project",
        "district": "Galle",
        "province": "Southern Province",
        "floors": 2,
        "building_type": "Residential",
    }
    project.update(overrides)
    return {"project": project, "phases": [_VALID_PHASE]}


# --- Length validation: oversized input must be a clean 400, not a DB 500 ---

def test_oversized_project_name_is_rejected():
    errors = _validate_schedule_payload(_valid_project(name="x" * 256))
    assert any("project.name" in e and "at most 255" in e for e in errors)


def test_project_name_at_limit_is_accepted():
    assert _validate_schedule_payload(_valid_project(name="x" * 255)) == []


def test_oversized_district_is_rejected():
    errors = _validate_schedule_payload(_valid_project(district="x" * 101))
    assert any("project.district" in e and "at most 100" in e for e in errors)


def test_oversized_province_is_rejected():
    errors = _validate_schedule_payload(_valid_project(province="x" * 101))
    assert any("project.province" in e and "at most 100" in e for e in errors)


def test_oversized_building_type_is_rejected():
    errors = _validate_schedule_payload(_valid_project(building_type="x" * 101))
    assert any("project.building_type" in e and "at most 100" in e for e in errors)


def test_oversized_sub_phase_is_rejected():
    phase = dict(_VALID_PHASE, sub_phase="x" * 101)
    data = _valid_project()
    data["phases"] = [phase]
    errors = _validate_schedule_payload(data)
    assert any("sub_phase" in e and "at most 100" in e for e in errors)


def test_valid_project_dict_still_works_unaffected():
    data = {
        "project": {
            "name": "Test Project",
            "district": "Galle",
            "province": "Southern Province",
            "floors": 2,
            "building_type": "Residential",
        },
        "phases": [_VALID_PHASE],
    }
    errors = _validate_schedule_payload(data)
    assert errors == []
