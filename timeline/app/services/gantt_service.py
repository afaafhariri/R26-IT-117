"""Gantt chart and milestone generation service."""

from datetime import date, datetime, timedelta
from typing import Any


DISPLAY_NAMES = {
    "foundation": "Foundation",
    "structure": "Structure",
    "masonry": "Masonry",
    "roofing": "Roofing",
    "electrical": "Electrical",
    "plumbing": "Plumbing",
    "plastering": "Plastering",
    "finishing": "Finishing",
    "painting": "Painting",
    "external_work": "External Work",
    "handover": "Handover",
    "electrical_plumbing": "Electrical and Plumbing",
}


def generate_gantt_chart_data(
    phase_durations: dict[str, int],
    start_finish: dict[str, dict[str, int]],
    planned_start_date: Any = None,
) -> list[dict]:
    """Return frontend-ready Gantt chart task data."""

    project_start = _parse_project_start_date(planned_start_date)
    gantt_data = []
    for index, phase in enumerate(
        ["foundation", "structure", "roofing", "electrical_plumbing", "finishing"],
        start=1,
    ):
        duration_days = max(1, int(phase_durations[phase] * 7))
        start_week = start_finish[phase]["start_week"]
        start_date = _date_from_start_week(project_start, start_week)
        end_date = start_date + timedelta(days=duration_days - 1)
        gantt_data.append(
            {
                "id": index,
                "task": DISPLAY_NAMES[phase],
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "start_week": start_week,
                "end_week": start_finish[phase]["end_week"],
                "duration_weeks": phase_durations[phase],
                "duration_days": duration_days,
            }
        )
    return gantt_data


def generate_milestones(start_finish: dict[str, dict[str, int]]) -> list[dict]:
    """Generate milestone list from phase completion weeks."""

    return [
        {
            "name": "Foundation Completed",
            "phase": "foundation",
            "week": start_finish["foundation"]["end_week"],
        },
        {
            "name": "Structure Completed",
            "phase": "structure",
            "week": start_finish["structure"]["end_week"],
        },
        {
            "name": "Roofing Completed",
            "phase": "roofing",
            "week": start_finish["roofing"]["end_week"],
        },
        {
            "name": "MEP Completed",
            "phase": "electrical_plumbing",
            "week": start_finish["electrical_plumbing"]["end_week"],
        },
        {
            "name": "Project Completed",
            "phase": "finishing",
            "week": start_finish["finishing"]["end_week"],
        },
    ]


def generate_gantt_chart_data_from_days(
    phase_days: dict[str, int],
    start_finish: dict[str, dict[str, int]],
    planned_start_date: Any = None,
) -> list[dict]:
    """Return Gantt chart tasks from detailed day-level predictions."""

    project_start = _parse_project_start_date(planned_start_date)
    ordered_tasks = [
        "foundation",
        "structure",
        "masonry",
        "roofing",
        "electrical",
        "plumbing",
        "plastering",
        "finishing",
        "painting",
        "external_work",
        "handover",
    ]
    gantt_data = []
    for index, task in enumerate(ordered_tasks, start=1):
        duration_days = int(phase_days[task])
        start_week = round(((start_finish[task]["start_day"] - 1) / 7) + 1, 2)
        end_week = round(((start_finish[task]["end_day"] - 1) / 7) + 1, 2)
        start_date = _date_from_start_week(project_start, start_week)
        end_date = start_date + timedelta(days=duration_days - 1)
        gantt_data.append(
            {
                "id": index,
                "task": DISPLAY_NAMES[task],
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "start_week": start_week,
                "end_week": end_week,
                "duration_weeks": round(duration_days / 7, 2),
                "duration_days": duration_days,
            }
        )
    return gantt_data


def generate_milestones_from_days(start_finish: dict[str, dict[str, int]]) -> list[dict]:
    """Generate milestone weeks from detailed day-level schedule output."""

    return [
        {
            "name": "Foundation Completed",
            "phase": "foundation",
            "week": int(round(start_finish["foundation"]["end_day"] / 7)),
        },
        {
            "name": "Structure Completed",
            "phase": "structure",
            "week": int(round(start_finish["structure"]["end_day"] / 7)),
        },
        {
            "name": "Roofing Completed",
            "phase": "roofing",
            "week": int(round(start_finish["roofing"]["end_day"] / 7)),
        },
        {
            "name": "MEP Completed",
            "phase": "electrical",
            "week": int(round(max(
                start_finish["electrical"]["end_day"],
                start_finish["plumbing"]["end_day"],
            ) / 7)),
        },
        {
            "name": "Project Completed",
            "phase": "handover",
            "week": int(round(start_finish["handover"]["end_day"] / 7)),
        },
    ]


def _parse_project_start_date(value: Any) -> date:
    """Parse the requested project start date, defaulting to today."""

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


def _date_from_start_week(project_start: date, start_week: int | float) -> date:
    """Convert a 1-based schedule week into an actual calendar start date."""

    offset_days = int(round((float(start_week) - 1) * 7))
    return project_start + timedelta(days=max(0, offset_days))
