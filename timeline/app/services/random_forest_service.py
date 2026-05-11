"""Trained model integration for timeline prediction.

XGBoost is preferred as the main phase duration model. Random Forest remains
available as the fallback trained model.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


BASE_DIR = Path(__file__).resolve().parents[2]
XGBOOST_MODEL_PATH = BASE_DIR / "models" / "timeline_xgboost_model.pkl"
RANDOM_FOREST_MODEL_PATH = BASE_DIR / "models" / "timeline_random_forest_model.pkl"

INPUT_FEATURES = [
    "num_floors",
    "floor_area_sqm",
    "built_up_area_sqft",
    "room_count",
    "bathroom_count",
    "foundation_excavation_m3",
    "foundation_concrete_m3",
    "total_concrete_m3",
    "steel_kg_estimate",
    "total_brickwork_m3",
    "roof_area_sqm",
    "floor_tile_sqm",
    "wall_plaster_sqm",
    "paint_sqm",
    "electrical_points",
    "total_plumbing_fixtures",
    "total_labour_days",
    "structural_complexity_score",
]

TARGET_COLUMNS = [
    "foundation_days",
    "structure_days",
    "masonry_days",
    "roofing_days",
    "electrical_days",
    "plumbing_days",
    "plastering_days",
    "finishing_days",
    "painting_days",
    "external_work_days",
    "handover_days",
    "total_duration_days",
]

DAY_TO_PHASE = {
    "foundation_days": "foundation",
    "structure_days": "structure",
    "masonry_days": "masonry",
    "roofing_days": "roofing",
    "electrical_days": "electrical",
    "plumbing_days": "plumbing",
    "plastering_days": "plastering",
    "finishing_days": "finishing",
    "painting_days": "painting",
    "external_work_days": "external_work",
    "handover_days": "handover",
}


def is_cost_estimation_payload(payload: dict[str, Any]) -> bool:
    """Return True when the payload resembles Cost Estimation output."""

    return any(
        key in payload
        for key in ("boq_summary", "feeds_downstream", "summary", "risk_factors_applied")
    )


def load_model_package(model_path: Path) -> dict | None:
    """Load a saved model package if it exists."""

    if not model_path.exists():
        return None

    try:
        import joblib

        package = joblib.load(model_path)
        if isinstance(package, dict) and "model" in package:
            return package
        return {"model": package, "input_features": INPUT_FEATURES, "target_columns": TARGET_COLUMNS}
    except Exception:
        return None


def load_random_forest_model() -> dict | None:
    """Load the saved Random Forest package if it exists."""

    return load_model_package(RANDOM_FOREST_MODEL_PATH)


def load_xgboost_model() -> dict | None:
    """Load the saved XGBoost package if it exists."""

    return load_model_package(XGBOOST_MODEL_PATH)


def predict_with_best_available_model(payload: dict[str, Any]) -> dict | None:
    """
    Predict using XGBoost first, then Random Forest.

    Returns None only if both trained models are unavailable or fail, allowing
    the rule-based service to remain the final safety net.
    """

    xgb_package = load_xgboost_model()
    if xgb_package is not None:
        prediction = predict_with_model_package(payload, xgb_package, "xgboost")
        if prediction is not None:
            prediction["phase_duration_model"] = "xgboost"
            prediction["xgboost_status"] = "trained model used"
            prediction["random_forest_status"] = "fallback available"
            return prediction

    rf_package = load_random_forest_model()
    if rf_package is not None:
        prediction = predict_with_model_package(payload, rf_package, "random_forest")
        if prediction is not None:
            prediction["phase_duration_model"] = "random_forest"
            prediction["xgboost_status"] = "fallback used - xgboost unavailable or failed"
            prediction["random_forest_status"] = "trained fallback model used"
            return prediction

    return None


def predict_with_random_forest(payload: dict[str, Any]) -> dict | None:
    """
    Build the feature vector, run the trained model, and return phase durations.

    Any failure returns None so the timeline service can safely use the
    rule-based fallback.
    """

    package = load_random_forest_model()
    if package is None:
        return None

    return predict_with_model_package(payload, package, "random_forest")


def predict_with_model_package(
    payload: dict[str, Any],
    package: dict,
    model_name: str,
) -> dict | None:
    """Run prediction using a loaded model package."""

    try:
        features = build_feature_vector(payload)
        feature_order = package.get("input_features", INPUT_FEATURES)
        target_order = package.get("target_columns", TARGET_COLUMNS)
        X = pd.DataFrame([[features[name] for name in feature_order]], columns=feature_order)
        raw_prediction = package["model"].predict(X)[0]

        predictions = {
            target: max(1, int(round(float(value))))
            for target, value in zip(target_order, raw_prediction)
        }

        days = {
            DAY_TO_PHASE[column]: predictions[column]
            for column in TARGET_COLUMNS
            if column != "total_duration_days"
        }
        total_days = max(1, int(predictions["total_duration_days"]))

        return {
            "phase_duration_model": model_name,
            "features": features,
            "predicted_phase_durations_days": days,
            "total_project_duration_days": total_days,
        }
    except Exception:
        return None


def build_feature_vector(payload: dict[str, Any]) -> dict[str, float]:
    """Extract the exact model feature vector from Cost Estimation output."""

    structural = nested_dict(payload, "boq_summary", "structural")
    finishing = nested_dict(payload, "boq_summary", "finishing")
    services = nested_dict(payload, "boq_summary", "services")
    aggregates = nested_dict(payload, "boq_summary", "aggregates")
    feeds = nested_dict(payload, "feeds_downstream")
    summary = nested_dict(payload, "summary")
    risks = nested_dict(payload, "risk_factors_applied")

    built_up_area_sqft = first_number(
        payload,
        feeds,
        summary,
        keys=("built_up_area_sqft", "built_up_area", "total_floor_area_sqft", "area_sqft"),
        default=2000.0,
    )
    floor_area_sqm = first_number(
        payload,
        feeds,
        summary,
        keys=("floor_area_sqm", "total_floor_area_sqm", "area_sqm"),
        default=built_up_area_sqft / 10.7639,
    )
    if floor_area_sqm > 700 and built_up_area_sqft <= 5000:
        # Some upstream components may send square feet under a sqm-like key.
        floor_area_sqm = floor_area_sqm / 10.7639

    num_floors = int(
        first_number(
            payload,
            feeds,
            summary,
            keys=("num_floors", "number_of_floors", "floors"),
            default=1,
        )
    )
    room_count = int(
        first_number(
            payload,
            feeds,
            summary,
            keys=("room_count", "num_rooms", "rooms"),
            default=max(2, round(floor_area_sqm / 45)),
        )
    )
    bathroom_count = int(
        first_number(
            payload,
            feeds,
            summary,
            keys=("bathroom_count", "num_bathrooms", "bathrooms"),
            default=max(1, round(room_count / 2.5)),
        )
    )

    foundation_excavation_m3 = first_number(
        structural,
        aggregates,
        keys=("foundation_excavation_m3", "excavation_m3", "earthwork_m3"),
        default=floor_area_sqm * (0.28 + 0.08 * num_floors),
    )
    foundation_concrete_m3 = first_number(
        structural,
        aggregates,
        keys=("foundation_concrete_m3", "foundation_concrete", "concrete_foundation_m3"),
        default=floor_area_sqm * (0.12 + 0.04 * num_floors),
    )
    total_concrete_m3 = first_number(
        structural,
        aggregates,
        keys=("total_concrete_m3", "concrete_m3", "rcc_concrete_m3"),
        default=foundation_concrete_m3 + floor_area_sqm * num_floors * 0.18,
    )
    steel_kg_estimate = first_number(
        structural,
        aggregates,
        keys=("steel_kg_estimate", "steel_kg", "reinforcement_kg"),
        default=floor_area_sqm * num_floors * (28 + 7 * num_floors),
    )
    total_brickwork_m3 = first_number(
        structural,
        aggregates,
        keys=("total_brickwork_m3", "brickwork_m3", "masonry_m3"),
        default=floor_area_sqm * num_floors * (0.18 + room_count * 0.012),
    )
    roof_area_sqm = first_number(
        structural,
        aggregates,
        keys=("roof_area_sqm", "roof_sqm"),
        default=floor_area_sqm * 1.12,
    )
    floor_tile_sqm = first_number(
        finishing,
        aggregates,
        keys=("floor_tile_sqm", "tiles_sqm", "tile_area_sqm"),
        default=floor_area_sqm * num_floors * 0.82,
    )
    wall_plaster_sqm = first_number(
        finishing,
        aggregates,
        keys=("wall_plaster_sqm", "plaster_sqm", "plastering_sqm"),
        default=floor_area_sqm * num_floors * (2.35 + room_count * 0.08),
    )
    paint_sqm = first_number(
        finishing,
        aggregates,
        keys=("paint_sqm", "painting_sqm", "paint_area_sqm"),
        default=wall_plaster_sqm * 0.92,
    )
    electrical_points = first_number(
        services,
        aggregates,
        keys=("electrical_points", "electric_points", "light_points", "power_points"),
        default=room_count * 5.5 + bathroom_count * 2.5 + num_floors * 5,
    )
    total_plumbing_fixtures = first_number(
        services,
        aggregates,
        keys=("total_plumbing_fixtures", "plumbing_fixtures", "sanitary_fixtures"),
        default=bathroom_count * 4 + num_floors * 1.5,
    )
    total_labour_days = first_number(
        payload,
        feeds,
        summary,
        keys=("total_labour_days", "labor_days", "labour_days", "estimated_labour_days"),
        default=estimate_labour_days(
            floor_area_sqm,
            num_floors,
            total_concrete_m3,
            total_brickwork_m3,
            floor_tile_sqm,
            paint_sqm,
            electrical_points,
            total_plumbing_fixtures,
        ),
    )
    structural_complexity_score = first_number(
        feeds,
        summary,
        risks,
        keys=("structural_complexity_score", "complexity_score", "design_complexity_score"),
        default=1.0 + (num_floors - 1) * 0.45 + (floor_area_sqm / 400.0) * 0.45 + (room_count / 8.0) * 0.25,
    )

    return {
        "num_floors": max(1, float(num_floors)),
        "floor_area_sqm": max(1.0, float(floor_area_sqm)),
        "built_up_area_sqft": max(1.0, float(built_up_area_sqft)),
        "room_count": max(1, float(room_count)),
        "bathroom_count": max(1, float(bathroom_count)),
        "foundation_excavation_m3": max(0.0, float(foundation_excavation_m3)),
        "foundation_concrete_m3": max(0.0, float(foundation_concrete_m3)),
        "total_concrete_m3": max(0.0, float(total_concrete_m3)),
        "steel_kg_estimate": max(0.0, float(steel_kg_estimate)),
        "total_brickwork_m3": max(0.0, float(total_brickwork_m3)),
        "roof_area_sqm": max(0.0, float(roof_area_sqm)),
        "floor_tile_sqm": max(0.0, float(floor_tile_sqm)),
        "wall_plaster_sqm": max(0.0, float(wall_plaster_sqm)),
        "paint_sqm": max(0.0, float(paint_sqm)),
        "electrical_points": max(0.0, float(electrical_points)),
        "total_plumbing_fixtures": max(0.0, float(total_plumbing_fixtures)),
        "total_labour_days": max(0.0, float(total_labour_days)),
        "structural_complexity_score": max(1.0, float(structural_complexity_score)),
    }


def nested_dict(data: dict[str, Any], *keys: str) -> dict[str, Any]:
    """Safely return a nested dictionary or an empty dict."""

    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return {}
        current = current.get(key, {})
    return current if isinstance(current, dict) else {}


def first_number(*sources: dict[str, Any], keys: tuple[str, ...], default: float) -> float:
    """Find the first numeric value for any key in the provided source dicts."""

    for source in sources:
        if not isinstance(source, dict):
            continue
        value = find_key_recursive(source, keys)
        if value is not None:
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
    return float(default)


def find_key_recursive(data: dict[str, Any], keys: tuple[str, ...]) -> Any:
    """Search nested dictionaries for one of several accepted field names."""

    normalized_keys = {normalize_key(key) for key in keys}
    for key, value in data.items():
        if normalize_key(str(key)) in normalized_keys:
            return value
        if isinstance(value, dict):
            nested_value = find_key_recursive(value, keys)
            if nested_value is not None:
                return nested_value
    return None


def normalize_key(key: str) -> str:
    """Normalize upstream key variants for robust extraction."""

    return key.lower().replace(" ", "_").replace("-", "_")


def estimate_labour_days(
    floor_area_sqm: float,
    num_floors: int,
    total_concrete_m3: float,
    total_brickwork_m3: float,
    floor_tile_sqm: float,
    paint_sqm: float,
    electrical_points: float,
    total_plumbing_fixtures: float,
) -> float:
    """Estimate labour days when upstream cost output does not provide it."""

    return (
        floor_area_sqm * num_floors * 1.65
        + total_concrete_m3 * 1.4
        + total_brickwork_m3 * 1.9
        + floor_tile_sqm * 0.18
        + paint_sqm * 0.10
        + electrical_points * 0.9
        + total_plumbing_fixtures * 1.3
    )
