"""Format planned schedule output for the downstream performance component."""

from datetime import date, datetime, timedelta
from typing import Any


PHASE_MONITORING_MAP = [
    {
        "phase": "foundation",
        "phase_group": "Foundations",
        "sub_phase": "Foundation work",
    },
    {
        "phase": "structure",
        "phase_group": "Structure",
        "sub_phase": "Columns, beams and slab work",
    },
    {
        "phase": "masonry",
        "phase_group": "Envelope & Waterproofing",
        "sub_phase": "Masonry work",
    },
    {
        "phase": "roofing",
        "phase_group": "Envelope & Waterproofing",
        "sub_phase": "Roofing / roof slab work",
    },
    {
        "phase": "electrical",
        "phase_group": "MEP Rough-Ins",
        "sub_phase": "Electrical conduit work",
    },
    {
        "phase": "plumbing",
        "phase_group": "MEP Rough-Ins",
        "sub_phase": "Plumbing and drainage work",
    },
    {
        "phase": "plastering",
        "phase_group": "Finishes",
        "sub_phase": "Internal plastering",
    },
    {
        "phase": "finishing",
        "phase_group": "Finishes",
        "sub_phase": "Tiling and finishing work",
    },
    {
        "phase": "painting",
        "phase_group": "Finishes",
        "sub_phase": "Painting",
    },
    {
        "phase": "external_work",
        "phase_group": "External Works & Handover",
        "sub_phase": "External works",
    },
    {
        "phase": "handover",
        "phase_group": "External Works & Handover",
        "sub_phase": "Client handover",
    },
]

GANTT_TASK_TO_MONITORING = {
    "Foundation": {
        "phase_group": "Foundations",
        "sub_phase": "Foundation work",
    },
    "Structure": {
        "phase_group": "Structure",
        "sub_phase": "Columns, beams and slab work",
    },
    "Masonry": {
        "phase_group": "Envelope & Waterproofing",
        "sub_phase": "Masonry work",
    },
    "Roofing": {
        "phase_group": "Envelope & Waterproofing",
        "sub_phase": "Roofing / roof slab work",
    },
    "Electrical": {
        "phase_group": "MEP Rough-Ins",
        "sub_phase": "Electrical conduit work",
    },
    "Plumbing": {
        "phase_group": "MEP Rough-Ins",
        "sub_phase": "Plumbing and drainage work",
    },
    "Plastering": {
        "phase_group": "Finishes",
        "sub_phase": "Internal plastering",
    },
    "Finishing": {
        "phase_group": "Finishes",
        "sub_phase": "Tiling and finishing work",
    },
    "Painting": {
        "phase_group": "Finishes",
        "sub_phase": "Painting",
    },
    "External Work": {
        "phase_group": "External Works & Handover",
        "sub_phase": "External works",
    },
    "Handover": {
        "phase_group": "External Works & Handover",
        "sub_phase": "Client handover",
    },
    "Electrical and Plumbing": {
        "phase_group": "MEP Rough-Ins",
        "sub_phase": "Electrical and plumbing work",
    },
}


def build_performance_monitoring_payload(
    request_payload: dict[str, Any],
    phase_days: dict[str, int],
    total_project_duration_days: int | None = None,
    gantt_chart_data: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build the planned schedule JSON contract expected by the next component."""

    planned_start = _parse_planned_start_date(
        request_payload.get("planned_start_date")
    )
    monitoring_phases = _phases_from_gantt(gantt_chart_data)
    if not monitoring_phases:
        monitoring_phases = _sequential_phases_from_days(planned_start, phase_days)

    total_planned_duration_days = _positive_duration_days(
        total_project_duration_days
    )
    gantt_end_date = _final_gantt_end_date(gantt_chart_data)
    if total_planned_duration_days is None:
        planned_end_date = gantt_end_date or (
            monitoring_phases[-1]["planned_end"]
            if monitoring_phases
            else planned_start.isoformat()
        )
        total_planned_duration_days = _inclusive_days(
            planned_start.isoformat(),
            planned_end_date,
        )
    else:
        planned_end_date = gantt_end_date or (
            planned_start + timedelta(days=total_planned_duration_days - 1)
        ).isoformat()

    rate_metadata = _as_dict(request_payload.get("rate_metadata"))
    feeds_downstream = _as_dict(request_payload.get("feeds_downstream"))
    scope_summary = _construction_scope_summary(request_payload, feeds_downstream)

    return {
        "project_id": request_payload.get("project_id"),
        "project_name": request_payload.get("project_name"),
        "district": request_payload.get("district")
        or rate_metadata.get("district")
        or "Unknown",
        "province": rate_metadata.get("province") or "Unknown",
        "floors": scope_summary["timeline_required_floors"],
        "planned_total_floors": scope_summary["planned_total_floors"],
        "construction_scope": scope_summary,
        "building_type": (
            request_payload.get("building_type")
            or feeds_downstream.get("building_type")
            or "residential"
        ),
        "total_planned_duration_days": total_planned_duration_days,
        "planned_start_date": planned_start.isoformat(),
        "planned_end_date": planned_end_date,
        "phases": monitoring_phases,
    }


def _phases_from_gantt(
    gantt_chart_data: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Build downstream phases directly from Gantt task dates."""

    if not isinstance(gantt_chart_data, list):
        return []

    phases = []
    for sequence, item in enumerate(gantt_chart_data, start=1):
        if not isinstance(item, dict):
            continue

        task = str(item.get("task") or "").strip()
        mapping = GANTT_TASK_TO_MONITORING.get(task)
        start_date = _iso_date_string(item.get("start_date"))
        end_date = _iso_date_string(item.get("end_date"))
        duration_days = _positive_duration_days(item.get("duration_days"))
        if not mapping or not start_date or not end_date or duration_days is None:
            continue

        phases.append(
            {
                "phase_id": sequence,
                "phase_group": mapping["phase_group"],
                "sub_phase": mapping["sub_phase"],
                "planned_start": start_date,
                "planned_end": end_date,
                "planned_duration_days": duration_days,
                "sequence": sequence,
            }
        )

    return phases


def _sequential_phases_from_days(
    planned_start: date,
    phase_days: dict[str, int],
) -> list[dict[str, Any]]:
    """Fallback phase dates used only when Gantt data is unavailable."""

    current_start = planned_start
    monitoring_phases = []
    for sequence, phase_info in enumerate(PHASE_MONITORING_MAP, start=1):
        phase_name = phase_info["phase"]
        if phase_name not in phase_days:
            continue

        duration_days = max(1, int(round(phase_days[phase_name])))
        planned_end = current_start + timedelta(days=duration_days - 1)
        monitoring_phases.append(
            {
                "phase_id": sequence,
                "phase_group": phase_info["phase_group"],
                "sub_phase": phase_info["sub_phase"],
                "planned_start": current_start.isoformat(),
                "planned_end": planned_end.isoformat(),
                "planned_duration_days": duration_days,
                "sequence": sequence,
            }
        )
        current_start = planned_end + timedelta(days=1)
    return monitoring_phases


def _final_gantt_end_date(gantt_chart_data: list[dict[str, Any]] | None) -> str | None:
    """Return handover end date from Gantt data, or the latest task end date."""

    if not isinstance(gantt_chart_data, list):
        return None

    valid_items = [
        item for item in gantt_chart_data
        if isinstance(item, dict) and _iso_date_string(item.get("end_date"))
    ]
    if not valid_items:
        return None

    for item in valid_items:
        if str(item.get("task") or "").strip() == "Handover":
            return _iso_date_string(item.get("end_date"))

    latest = max(
        valid_items,
        key=lambda item: date.fromisoformat(_iso_date_string(item.get("end_date"))),
    )
    return _iso_date_string(latest.get("end_date"))


def _parse_planned_start_date(value: Any) -> date:
    """Parse a planned start date, defaulting to today's local date."""

    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return date.fromisoformat(value.strip()[:10])
        except ValueError:
            return date.today()
    return date.today()


def _extract_floors(
    feeds_downstream: dict[str, Any],
    request_payload: dict[str, Any],
) -> int:
    """Read floors using the downstream contract fallback order."""

    parsed = _to_positive_int(request_payload.get("floors"))
    if parsed is not None:
        return parsed

    parsed = _to_positive_int(feeds_downstream.get("floors"))
    if parsed is not None:
        return parsed

    risks = _as_dict(request_payload.get("risk_factors_applied"))
    if "multi_storey" in risks:
        return 2

    return 1


def _construction_scope_summary(
    request_payload: dict[str, Any],
    feeds_downstream: dict[str, Any],
) -> dict[str, Any]:
    """Return floor scope metadata for downstream planned schedule consumers."""

    scope = _as_dict(request_payload.get("construction_scope"))
    fallback_floors = _extract_floors(feeds_downstream, request_payload)

    planned_total_floors = _to_positive_int(
        scope.get("planned_total_floors")
        or request_payload.get("planned_total_floors")
    ) or fallback_floors
    timeline_required_floors = _to_positive_int(
        scope.get("timeline_required_floors")
        or request_payload.get("timeline_required_floors")
    ) or fallback_floors

    planned_total_floors = max(planned_total_floors, timeline_required_floors)
    scope_type = scope.get("scope_type") or (
        "partial_construction"
        if timeline_required_floors < planned_total_floors
        else "full_construction"
    )

    return {
        "planned_total_floors": planned_total_floors,
        "timeline_required_floors": timeline_required_floors,
        "scope_type": scope_type,
        "scope_description": scope.get("scope_description"),
        "message": "Timeline generated for selected construction scope only",
    }


def _inclusive_days(start_iso: str, end_iso: str) -> int:
    """Return inclusive calendar days between two ISO dates."""

    start_date = date.fromisoformat(start_iso)
    end_date = date.fromisoformat(end_iso)
    return max(1, (end_date - start_date).days + 1)


def _as_dict(value: Any) -> dict[str, Any]:
    """Return value if it is a dictionary, otherwise an empty dictionary."""

    return value if isinstance(value, dict) else {}


def _to_positive_int(value: Any) -> int | None:
    """Convert a value to a positive integer when possible."""

    if value is None:
        return None
    try:
        parsed = int(float(value))
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _positive_duration_days(value: Any) -> int | None:
    """Convert a scheduled duration to a positive integer day count."""

    if value is None:
        return None
    try:
        parsed = int(round(float(value)))
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _iso_date_string(value: Any) -> str | None:
    """Return a valid ISO date string when possible."""

    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str) and value.strip():
        candidate = value.strip()[:10]
        try:
            return date.fromisoformat(candidate).isoformat()
        except ValueError:
            return None
    return None
