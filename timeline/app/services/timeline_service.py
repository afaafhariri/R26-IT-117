"""Main orchestration service for timeline prediction."""

from typing import Any

from app.models.schemas import TimelinePredictionRequest
from app.services.cpm_service import (
    calculate_cpm,
    calculate_cpm_days,
    get_day_task_dependencies,
    get_task_dependencies,
)
from app.services.gantt_service import (
    generate_gantt_chart_data,
    generate_gantt_chart_data_from_days,
    generate_milestones,
    generate_milestones_from_days,
)
from app.services.lstm_service import predict_timeline_with_lstm_placeholder
from app.services.lstm_service import predict_total_duration_with_lstm
from app.services.ml_service import (
    estimate_confidence_score,
    predict_phase_durations_rule_based,
)
from app.services.performance_format_service import build_performance_monitoring_payload
from app.services.random_forest_service import (
    is_cost_estimation_payload,
    predict_with_best_available_model,
)
from app.services.resource_service import create_resource_allocation_plan


def generate_timeline_prediction(payload: dict[str, Any]) -> dict:
    """Run Random Forest prediction first, then fallback to rule-based logic."""

    payload = _normalize_project_identity(payload)

    if is_cost_estimation_payload(payload):
        model_prediction = predict_with_best_available_model(payload)
        if model_prediction is not None:
            return _generate_trained_model_response(payload, model_prediction)

    request = TimelinePredictionRequest(**payload)
    return _generate_rule_based_response(request, fallback_reason="random forest unavailable")


def _generate_rule_based_response(
    request: TimelinePredictionRequest,
    fallback_reason: str,
) -> dict:
    """Generate response using the original transparent rule-based baseline."""

    phase_durations = predict_phase_durations_rule_based(request)
    cpm_result = calculate_cpm(phase_durations)
    total_duration = cpm_result["total_project_duration_weeks"]

    lstm_result = predict_timeline_with_lstm_placeholder(
        {
            **phase_durations,
            "total_project_duration_days": int(total_duration * 7),
            "total_project_duration_weeks": total_duration,
        },
        request,
    )
    phase_days = {
        phase: int(weeks * 7)
        for phase, weeks in phase_durations.items()
    }
    performance_monitoring_payload = build_performance_monitoring_payload(
        request_payload=request.model_dump(),
        phase_days=phase_days,
    )

    return {
        "project_id": request.project_id,
        "project_name": request.project_name,
        "predicted_phase_durations_days": phase_days,
        "predicted_phase_durations_weeks": phase_durations,
        "total_project_duration_days": int(total_duration * 7),
        "total_project_duration_weeks": total_duration,
        "model_predictions": {
            "phase_duration_model": "rule_based",
            "xgboost_status": f"fallback used - {fallback_reason}",
            "random_forest_status": f"fallback used - {fallback_reason}",
            "lstm_status": lstm_result["lstm_status"],
            "lstm_predicted_total_duration_days": lstm_result[
                "lstm_predicted_total_duration_days"
            ],
            "lstm_predicted_total_duration_weeks": lstm_result[
                "lstm_predicted_total_duration_weeks"
            ],
            "scheduled_total_duration_days": int(total_duration * 7),
            "scheduled_total_duration_weeks": total_duration,
        },
        "task_dependencies": get_task_dependencies(),
        "critical_path": cpm_result["critical_path"],
        "milestones": generate_milestones(cpm_result["start_finish"]),
        "gantt_chart_data": generate_gantt_chart_data(
            phase_durations,
            cpm_result["start_finish"],
            request.planned_start_date,
        ),
        "resource_allocation_plan": create_resource_allocation_plan(
            request.labor_requirements
        ),
        "performance_monitoring_payload": performance_monitoring_payload,
        "confidence_score": estimate_confidence_score(request),
        "message": "Timeline prediction generated successfully",
    }


def _generate_trained_model_response(
    payload: dict[str, Any],
    model_prediction: dict[str, Any],
) -> dict:
    """Generate the API response from trained model predictions."""

    raw_phase_days = model_prediction["predicted_phase_durations_days"]
    input_summary = _build_input_summary(payload, model_prediction.get("features", {}))
    phase_days = _apply_labour_count_adjustment(
        raw_phase_days,
        input_summary["labour_count"],
    )
    input_summary["labour_adjustment_applied"] = _labour_adjustment_label(
        input_summary["labour_count"]
    )
    total_days = model_prediction["total_project_duration_days"]
    cpm_result = calculate_cpm_days(phase_days)
    total_duration_days = cpm_result["total_project_duration_days"]

    # Prefer CPM total because it respects overlap; keep RF total in phase output.
    total_duration_weeks = cpm_result["total_project_duration_weeks"]
    phase_weeks = {
        phase: round(days / 7, 2)
        for phase, days in phase_days.items()
    }

    lstm_result = predict_total_duration_with_lstm(
        phase_days=phase_days,
        scheduled_total_duration_days=total_duration_days,
        scheduled_total_duration_weeks=total_duration_weeks,
    )
    performance_monitoring_payload = build_performance_monitoring_payload(
        request_payload=payload,
        phase_days=phase_days,
    )

    return {
        "project_id": str(payload.get("project_id")),
        "project_name": str(
            payload.get("project_name")
        ),
        "predicted_phase_durations_days": {
            **phase_days,
            "raw_model_total_duration_days": total_days,
        },
        "predicted_phase_durations_weeks": phase_weeks,
        "total_project_duration_days": total_duration_days,
        "total_project_duration_weeks": total_duration_weeks,
        "input_summary": input_summary,
        "model_predictions": {
            "phase_duration_model": model_prediction["phase_duration_model"],
            "xgboost_status": model_prediction["xgboost_status"],
            "random_forest_status": model_prediction["random_forest_status"],
            "lstm_status": lstm_result["lstm_status"],
            "lstm_predicted_total_duration_days": lstm_result[
                "lstm_predicted_total_duration_days"
            ],
            "lstm_predicted_total_duration_weeks": lstm_result[
                "lstm_predicted_total_duration_weeks"
            ],
            "scheduled_total_duration_days": total_duration_days,
            "scheduled_total_duration_weeks": total_duration_weeks,
        },
        "task_dependencies": get_day_task_dependencies(),
        "critical_path": cpm_result["critical_path"],
        "milestones": generate_milestones_from_days(cpm_result["start_finish"]),
        "gantt_chart_data": generate_gantt_chart_data_from_days(
            phase_days,
            cpm_result["start_finish"],
            payload.get("planned_start_date"),
        ),
        "resource_allocation_plan": _resource_plan_from_payload(payload),
        "performance_monitoring_payload": performance_monitoring_payload,
        "confidence_score": 0.88,
        "message": "Timeline prediction generated successfully",
    }


def _apply_labour_count_adjustment(
    phase_days: dict[str, int],
    labour_count: float | int | None,
) -> dict[str, int]:
    """Adjust phase durations after ML prediction based on available labour."""

    if labour_count is None:
        return dict(phase_days)

    if labour_count < 12:
        factor = 1.10
    elif labour_count > 24:
        factor = 0.95
    else:
        factor = 1.00

    return {
        phase: max(1, int(round(days * factor)))
        for phase, days in phase_days.items()
    }


def _labour_adjustment_label(labour_count: float | int | None) -> str:
    """Return a human-readable label for the labour adjustment."""

    if labour_count is None:
        return "no adjustment"
    if labour_count < 12:
        return "increased by 10%"
    if labour_count > 24:
        return "reduced by 5%"
    return "no adjustment"


def _build_input_summary(
    payload: dict[str, Any],
    features: dict[str, float],
) -> dict[str, float | int | str | None]:
    """Build summary values used by dashboard/debugging consumers."""

    feeds = payload.get("feeds_downstream", {})
    if not isinstance(feeds, dict):
        feeds = {}

    labour_count = feeds.get("labour_count")
    if labour_count is not None:
        try:
            labour_count = int(float(labour_count))
        except (TypeError, ValueError):
            labour_count = None
    if labour_count is None:
        labour_count = 20

    return {
        "labour_count": labour_count,
        "total_labour_days": _summary_number(
            feeds,
            features,
            "total_labour_days",
        ),
        "structural_complexity_score": _summary_number(
            feeds,
            features,
            "structural_complexity_score",
        ),
        "floor_area_sqm": _summary_number(
            feeds,
            features,
            "floor_area_sqm",
        ),
        "labour_adjustment_applied": "no adjustment",
    }


def _summary_number(
    feeds: dict[str, Any],
    features: dict[str, float],
    key: str,
) -> float | int | None:
    """Read a summary number from feeds_downstream or extracted model features."""

    value = feeds.get(key, features.get(key))
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return int(numeric) if numeric.is_integer() else round(numeric, 4)


def _resource_plan_from_payload(payload: dict[str, Any]) -> dict[str, dict]:
    """Create a resource plan from Cost Estimation output if labour details exist."""

    try:
        request = TimelinePredictionRequest(**payload)
        return create_resource_allocation_plan(request.labor_requirements)
    except Exception:
        labour = payload.get("labor_requirements", {})
        feeds = payload.get("feeds_downstream", {})
        if not isinstance(labour, dict):
            labour = {}
        if isinstance(feeds, dict):
            labour = {**feeds.get("labor_requirements", {}), **labour}

        helpers = int(labour.get("helpers", labour.get("general_workers", 4)) or 4)
        masons = int(labour.get("masons", 4) or 4)
        carpenters = int(labour.get("carpenters", 2) or 2)
        electricians = int(labour.get("electricians", 2) or 2)
        plumbers = int(labour.get("plumbers", 2) or 2)
        painters = int(labour.get("painters", 2) or 2)

        return {
            "foundation": {
                "masons": min(masons, 4),
                "helpers": min(helpers, 5),
                "equipment": ["concrete_mixer", "excavator"],
            },
            "structure": {
                "masons": min(masons, 6),
                "helpers": min(helpers, 8),
                "carpenters": min(carpenters, 3),
                "equipment": ["concrete_mixer", "scaffolding"],
            },
            "roofing": {
                "carpenters": min(carpenters, 2),
                "helpers": min(helpers, 4),
                "equipment": ["scaffolding"],
            },
            "electrical_plumbing": {
                "electricians": min(electricians, 2),
                "plumbers": min(plumbers, 2),
                "helpers": min(helpers, 2),
            },
            "finishing": {
                "painters": min(painters, 3),
                "helpers": min(helpers, 4),
                "masons": min(masons, 2),
            },
        }


def _normalize_project_identity(payload: dict[str, Any]) -> dict[str, Any]:
    """Apply project_id/project_name fallbacks without changing prediction inputs."""

    normalized = dict(payload)
    if not normalized.get("project_id") and normalized.get("estimate_id"):
        normalized["project_id"] = normalized["estimate_id"]
    if not normalized.get("project_name"):
        normalized["project_name"] = "Residential Construction Project"
    return normalized
