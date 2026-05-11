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


def build_performance_monitoring_payload(
    request_payload: dict[str, Any],
    phase_days: dict[str, int],
) -> dict[str, Any]:
    """Build the planned schedule JSON contract expected by the next component."""

    planned_start = _parse_planned_start_date(
        request_payload.get("planned_start_date")
    )
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

    planned_end_date = (
        monitoring_phases[-1]["planned_end"]
        if monitoring_phases
        else planned_start.isoformat()
    )
    total_planned_duration_days = _inclusive_days(
        planned_start.isoformat(),
        planned_end_date,
    )

    rate_metadata = _as_dict(request_payload.get("rate_metadata"))
    feeds_downstream = _as_dict(request_payload.get("feeds_downstream"))

    return {
        "project_id": request_payload.get("project_id"),
        "project_name": request_payload.get("project_name"),
        "district": request_payload.get("district")
        or rate_metadata.get("district")
        or "Unknown",
        "province": rate_metadata.get("province") or "Unknown",
        "floors": _extract_floors(feeds_downstream, request_payload),
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
