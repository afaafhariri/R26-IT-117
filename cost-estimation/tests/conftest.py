"""Shared pytest fixtures for Component 02 tests."""

import pytest


@pytest.fixture
def sample_building_schema() -> dict:
    """Minimal but complete Building Schema as produced by Component 01."""
    return {
        "footprint_sqm": 150.0,
        "perimeter": 50.0,
        "floors": 2,
        "floor_height": 3.0,
        "wall_height": 3.0,
        "excavation_depth": 1.5,
        "column_count": 0,           # auto-derived
        "openings_sqm": 28.0,
        "internal_wall_length": 30.0,
        "finish_grade": "mid",
        "roof_type": "gable",
        "is_coastal": False,
        "terrain": "flat",
        "road_access": "paved",
        "plot_area": 400.0,
        "bathroom_count": 2,
        "room_count": 5,
        "rooms": {
            "living_room": 1,
            "master_bedroom": 1,
            "bedroom": 2,
            "kitchen": 1,
            "bathroom": 2,
        },
        "base_rate_date": "2024-10-01",
        "target_date": "2025-06-01",
    }


@pytest.fixture
def luxury_building_schema(sample_building_schema) -> dict:
    """Variant with luxury grade on a constrained coastal site."""
    schema = dict(sample_building_schema)
    schema.update(
        {
            "finish_grade": "luxury",
            "is_coastal": True,
            "floors": 3,
            "plot_area": 180.0,
        }
    )
    return schema


@pytest.fixture
def economy_building_schema(sample_building_schema) -> dict:
    """Single-storey economy build."""
    schema = dict(sample_building_schema)
    schema.update({"finish_grade": "economy", "floors": 1})
    return schema
