import pytest
@pytest.fixture
def sample_building_schema():
    return {
        "footprint_sqm": 150.0,
        "perimeter": 50.0,
        "floors": 2,
        "finish_grade": "mid",
        "district": "Colombo"
    }
