"""Shared pytest fixtures for Component 01 test suite."""

import pytest


@pytest.fixture
def sample_site_schema() -> dict:
    """Realistic site schema based on Plan No. 2362 (Ampara, 472.9 sqm, coastal)."""
    return {
        "plan_id": "PLAN-2362-AM-20260430",
        "plan_number": "2362",
        "district": "Ampara",
        "province": "Eastern",
        "area_sqm": 472.9,
        "scale": 500,
        "surveyor": "S.M. Perera",
        "lot_number": "7A",
        "road_access": "provincial",
        "is_coastal": True,
        "orientation_degrees": 15.0,
        "frontage_m": 0.18,
        "boundary_polygon": [
            [0.05, 0.05],
            [0.85, 0.05],
            [0.85, 0.90],
            [0.05, 0.90],
            [0.05, 0.05],
        ],
        "page_dimensions": {"width": 2480, "height": 3508},
        "coordinate_n": 7.298,
        "coordinate_e": 81.687,
        "licence_number": "SL/SURV/2021/1145",
    }


@pytest.fixture
def sample_buildable_zone() -> dict:
    """Realistic buildable zone for a ~472.9 sqm coastal plot, 2 floors."""
    return {
        "buildable_polygon": [
            [0.1, 0.1],
            [0.8, 0.1],
            [0.8, 0.85],
            [0.1, 0.85],
            [0.1, 0.1],
        ],
        "max_footprint_sqm": 185.2,
        "max_total_built_sqm": 370.4,
        "recommended_floors": 2,
        "setback_margins": {"front": 3.0, "rear": 1.5, "side": 1.0},
        "coverage_achieved": 0.39,
        "orientation": {
            "recommended_orientation_degrees": 195.0,
            "entrance_side": "south",
            "optimal_placement": {"x_offset_m": 0.0, "y_offset_m": 0.0},
            "solar_notes": "Orient south-facing rooms for morning light.",
        },
    }


@pytest.fixture
def sample_user_requirements() -> dict:
    """Standard medium-tier 3-bedroom modern house requirements."""
    return {
        "room_types": [
            "living_room",
            "kitchen",
            "master_bedroom",
            "bedroom",
            "bedroom",
            "bathroom",
        ],
        "room_count": 6,
        "garage": False,
        "floors": 2,
        "budget_tier": "medium",
        "style": "modern",
        "district": "Ampara",
        "is_coastal": True,
    }


@pytest.fixture
def sample_floor_plan() -> dict:
    """Realistic 3-bedroom floor plan dict with all required fields."""
    return {
        "layout_name": "Compact Modern",
        "layout_label": "balanced",
        "temperature": 0.7,
        "budget_tier": "medium",
        "plan_id": "PLAN-2362-AM-20260430",
        "total_area_sqm": 185.0,
        "space_notes": "Open-plan living and dining with cross-ventilation corridor.",
        "rooms": [
            {
                "name": "living_room",
                "area_sqm": 20.0,
                "floor": 1,
                "x_norm": 0.1,
                "y_norm": 0.1,
                "width_norm": 0.3,
                "height_norm": 0.25,
                "window_orientation": "south",
                "adjacencies": ["dining", "entrance"],
            },
            {
                "name": "dining",
                "area_sqm": 12.0,
                "floor": 1,
                "x_norm": 0.4,
                "y_norm": 0.1,
                "width_norm": 0.2,
                "height_norm": 0.2,
                "window_orientation": "east",
                "adjacencies": ["kitchen", "living_room"],
            },
            {
                "name": "kitchen",
                "area_sqm": 9.0,
                "floor": 1,
                "x_norm": 0.6,
                "y_norm": 0.1,
                "width_norm": 0.2,
                "height_norm": 0.2,
                "window_orientation": "north",
                "adjacencies": ["dining"],
            },
            {
                "name": "master_bedroom",
                "area_sqm": 15.0,
                "floor": 2,
                "x_norm": 0.1,
                "y_norm": 0.5,
                "width_norm": 0.25,
                "height_norm": 0.25,
                "window_orientation": "south",
                "adjacencies": ["bathroom"],
            },
            {
                "name": "bedroom",
                "area_sqm": 11.0,
                "floor": 2,
                "x_norm": 0.4,
                "y_norm": 0.5,
                "width_norm": 0.2,
                "height_norm": 0.22,
                "window_orientation": "north",
                "adjacencies": ["bathroom"],
            },
            {
                "name": "bathroom",
                "area_sqm": 5.0,
                "floor": 2,
                "x_norm": 0.65,
                "y_norm": 0.5,
                "width_norm": 0.12,
                "height_norm": 0.15,
                "window_orientation": None,
                "adjacencies": ["master_bedroom", "bedroom"],
            },
        ],
    }
