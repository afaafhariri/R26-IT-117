import json
from datetime import date, datetime

from sqlalchemy import text

from database.db import get_db_session
from timeline_source import get_timeline_provider

# Homeowner-facing phase status values.
STATUS_NOT_STARTED = "NOT_STARTED"
STATUS_ON_TRACK = "ON_TRACK"
STATUS_AT_RISK = "AT_RISK"
STATUS_OVERDUE = "OVERDUE"
STATUS_COMPLETED = "COMPLETED"


def _to_date_or_none(value):
    if value is None or isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def derive_phase_status(planned_end, actual_percent, alert_level, as_of: date = None) -> str:
    """
    Homeowner-facing phase status, combining the PLANNED SCHEDULE with the
    ACTUAL RECORDED PROGRESS.

    This exists because a calendar date alone says nothing about whether work
    happened. Previously a phase was labelled "complete" purely because its
    planned end date had passed, so every phase of every historical project
    displayed as complete even with zero recorded progress - actively
    misleading to a house owner.

    Rules (in order):
      - COMPLETED   : actual progress reached 100%. Only ever set from real
                      recorded progress, NEVER from the calendar - so a phase
                      with 0% progress can never appear completed.
      - OVERDUE     : past the planned end date and not yet at 100%.
      - NOT_STARTED : no progress recorded yet (and still within/ahead of plan).
      - AT_RISK     : work under way but SPI flagged WARNING or CRITICAL.
      - ON_TRACK    : work under way and SPI healthy (or not yet calculated).
    """
    as_of = as_of or date.today()
    planned_end = _to_date_or_none(planned_end)

    if actual_percent is not None and float(actual_percent) >= 100:
        return STATUS_COMPLETED
    if planned_end and as_of > planned_end:
        return STATUS_OVERDUE
    if actual_percent is None or float(actual_percent) <= 0:
        return STATUS_NOT_STARTED
    if alert_level in ("WARNING", "CRITICAL"):
        return STATUS_AT_RISK
    return STATUS_ON_TRACK


def _get_project(session, project_id: int):
    """
    ARCHITECTURE NOTE: sourced via TimelineProvider (timeline_source/), not
    direct SQL - Performance does not own project data long-term. See
    timeline_source/base.py.
    """
    return get_timeline_provider().get_project(project_id)


def _get_phases_with_latest_spi(session, project_id: int):
    """
    Phase/schedule fields come from TimelineProvider (Timeline-owned data,
    temporarily mocked - see timeline_source/base.py). The latest SPI per
    phase is genuinely Performance-owned data (spi_results table), so that
    part stays as direct SQL and is merged in with the timeline phases here
    in Python, rather than as a cross-table SQL JOIN.
    """
    phases = get_timeline_provider().list_phases(project_id)
    if not phases:
        return []

    phase_ids = [p["phase_id"] for p in phases]
    rows = session.execute(
        text(
            """
            SELECT DISTINCT ON (phase_id) phase_id, id, spi_value, alert_level, calculated_at
            FROM spi_results
            WHERE phase_id = ANY(:phase_ids)
            ORDER BY phase_id, calculated_at DESC
            """
        ),
        {"phase_ids": phase_ids},
    ).fetchall()
    latest_spi_by_phase = {
        row[0]: {
            "spi_id": row[1],
            "spi_value": row[2],
            "alert_level": row[3],
            "calculated_at": row[4].isoformat() if row[4] else None,
        }
        for row in rows
    }

    # Latest ACTUAL recorded progress per phase - Performance-owned data, and
    # the missing half of a truthful phase status (see derive_phase_status).
    progress_rows = session.execute(
        text(
            """
            SELECT DISTINCT ON (phase_id) phase_id, actual_percent, update_date, created_at
            FROM progress_updates
            WHERE phase_id = ANY(:phase_ids)
            ORDER BY phase_id, created_at DESC
            """
        ),
        {"phase_ids": phase_ids},
    ).fetchall()
    latest_progress_by_phase = {
        row[0]: {
            "actual_percent": row[1],
            "update_date": row[2].isoformat() if row[2] else None,
            "recorded_at": row[3].isoformat() if row[3] else None,
        }
        for row in progress_rows
    }

    result = []
    for phase in phases:
        spi = latest_spi_by_phase.get(phase["phase_id"])
        progress = latest_progress_by_phase.get(phase["phase_id"])
        actual_percent = progress["actual_percent"] if progress else None
        result.append(
            {
                "phase_id": phase["phase_id"],
                "sequence": phase["sequence"],
                "phase_group": phase["phase_group"],
                "sub_phase": phase["sub_phase"],
                "planned_start": phase["planned_start"],
                "planned_end": phase["planned_end"],
                "planned_duration_days": phase["planned_duration_days"],
                "expected_progress_percent": phase["expected_progress_percent"],
                "schedule_status": phase["schedule_status"],
                "status": derive_phase_status(
                    planned_end=phase["planned_end"],
                    actual_percent=actual_percent,
                    alert_level=spi["alert_level"] if spi else None,
                ),
                "actual_percent": actual_percent,
                "latest_progress": progress,
                "latest_spi": spi,
            }
        )
    return result


def _get_latest_prediction(session, project_id: int):
    """
    Which phase_ids belong to this project is Timeline-owned (via
    TimelineProvider); which prediction is latest among them is genuinely
    Performance-owned (`predictions` table), so that part stays direct SQL.
    """
    phase_ids = [p["phase_id"] for p in get_timeline_provider().list_phases(project_id)]
    if not phase_ids:
        return None

    row = session.execute(
        text(
            """
            SELECT id, phase_id, delay_risk, estimated_delay_days, predicted_at
            FROM predictions
            WHERE phase_id = ANY(:phase_ids)
            ORDER BY predicted_at DESC
            LIMIT 1
            """
        ),
        {"phase_ids": phase_ids},
    ).fetchone()
    if not row:
        return None
    return {
        "prediction_id": row[0],
        "phase_id": row[1],
        "delay_risk": row[2],
        "estimated_delay_days": row[3],
        "predicted_at": row[4].isoformat() if row[4] else None,
    }


def _get_latest_recommendation_for_prediction(session, prediction_id: int):
    row = session.execute(
        text(
            """
            SELECT id, prediction_id, explanation, recommendations, similar_cases_used, generated_at
            FROM recommendations
            WHERE prediction_id = :prediction_id
            ORDER BY generated_at DESC
            LIMIT 1
            """
        ),
        {"prediction_id": prediction_id},
    ).fetchone()
    if not row:
        return None

    recommendations = row[3]
    try:
        parsed = json.loads(recommendations) if recommendations else []
        if isinstance(parsed, dict) and "corrective_actions" in parsed:
            parsed = parsed["corrective_actions"]
    except Exception:
        parsed = recommendations

    # Fixes a known limitation: the dashboard previously did not return the
    # 3 similar historical cases used for a prediction's recommendation,
    # even though they were already being stored in this column.
    similar_cases_raw = row[4]
    try:
        similar_cases = json.loads(similar_cases_raw) if similar_cases_raw else []
    except Exception:
        similar_cases = []

    return {
        "recommendation_id": row[0],
        "prediction_id": row[1],
        "explanation": row[2],
        "recommendations": parsed,
        "similar_cases": similar_cases,
        "generated_at": row[5].isoformat() if row[5] else None,
    }


def _get_active_alerts(session, project_id: int):
    rows = session.execute(
        text(
            """
            SELECT id, phase_id, alert_type, message, created_at
            FROM alerts
            WHERE project_id = :project_id
              AND COALESCE(is_resolved, FALSE) = FALSE
            ORDER BY created_at DESC
            """
        ),
        {"project_id": project_id},
    ).fetchall()
    return [
        {
            "alert_id": row[0],
            "phase_id": row[1],
            "alert_type": row[2],
            "message": row[3],
            "created_at": row[4].isoformat() if row[4] else None,
        }
        for row in rows
    ]


def _get_progress_history(session, project_id: int):
    """
    Which phase_ids belong to this project is Timeline-owned (via
    TimelineProvider); progress_updates/spi_results are genuinely
    Performance-owned, so that part stays direct SQL.
    """
    phase_ids = [p["phase_id"] for p in get_timeline_provider().list_phases(project_id)]
    if not phase_ids:
        return []

    rows = session.execute(
        text(
            """
            SELECT pu.id, pu.phase_id, pu.update_date, pu.planned_percent, pu.actual_percent,
                   s.spi_value, s.alert_level, pu.entered_by
            FROM progress_updates pu
            LEFT JOIN spi_results s ON s.update_id = pu.id
            WHERE pu.phase_id = ANY(:phase_ids)
            ORDER BY pu.created_at DESC
            """
        ),
        {"phase_ids": phase_ids},
    ).fetchall()
    return [
        {
            "update_id": row[0],
            "phase_id": row[1],
            "update_date": row[2].isoformat() if row[2] else None,
            "planned_percent": row[3],
            "actual_percent": row[4],
            "spi_value": row[5],
            "alert_level": row[6],
            "entered_by": row[7],
        }
        for row in rows
    ]


def _build_project_summary(phases: list) -> dict:
    """
    Overall schedule figures for a project, DERIVED from its phases rather
    than stored. `projects.start_date` exists in the schema but is never
    populated (POST /schedule does not accept it), and there is no stored
    project-level end date or duration - so deriving here avoids inventing
    fields the backend does not really own.

    Returns nulls (not guesses) when phases carry no usable dates.
    """
    starts = [_to_date_or_none(p.get("planned_start")) for p in phases]
    ends = [_to_date_or_none(p.get("planned_end")) for p in phases]
    starts = [d for d in starts if d]
    ends = [d for d in ends if d]

    overall_start = min(starts) if starts else None
    overall_end = max(ends) if ends else None
    total_days = (overall_end - overall_start).days + 1 if (overall_start and overall_end) else None

    completed = sum(1 for p in phases if p.get("status") == STATUS_COMPLETED)

    return {
        "total_phases": len(phases),
        "completed_phases": completed,
        "overall_start": overall_start.isoformat() if overall_start else None,
        "overall_end": overall_end.isoformat() if overall_end else None,
        "total_duration_days": total_days,
    }


def build_project_dashboard(project_id: int) -> dict:
    session = get_db_session()
    try:
        project = _get_project(session, project_id)
        if not project:
            return {"success": False, "error": "Project not found."}

        phases = _get_phases_with_latest_spi(session, project_id)
        latest_prediction = _get_latest_prediction(session, project_id)
        latest_recommendation = None
        if latest_prediction:
            latest_recommendation = _get_latest_recommendation_for_prediction(
                session, latest_prediction["prediction_id"]
            )
        active_alerts = _get_active_alerts(session, project_id)
        progress_history = _get_progress_history(session, project_id)

        return {
            "success": True,
            "project": project,
            "project_summary": _build_project_summary(phases),
            "phases": phases,
            "latest_prediction": latest_prediction,
            "latest_recommendation": latest_recommendation,
            "active_alerts": active_alerts,
            "progress_history": progress_history,
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}
    finally:
        session.close()
