import json
from sqlalchemy import text

from database.db import get_db_session


def _get_project(session, project_id: int):
    row = session.execute(
        text(
            """
            SELECT id, name, district, province, floors, building_type
            FROM projects
            WHERE id = :project_id
            """
        ),
        {"project_id": project_id},
    ).fetchone()
    if not row:
        return None
    return {
        "project_id": row[0],
        "name": row[1],
        "district": row[2],
        "province": row[3],
        "floors": row[4],
        "building_type": row[5],
    }


def _get_phases_with_latest_spi(session, project_id: int):
    rows = session.execute(
        text(
            """
            SELECT p.id, p.sequence, p.phase_group, p.sub_phase,
                   p.planned_start, p.planned_end, p.planned_duration_days,
                   s.id AS spi_id, s.spi_value, s.alert_level, s.calculated_at
            FROM phases p
            LEFT JOIN LATERAL (
                SELECT id, spi_value, alert_level, calculated_at
                FROM spi_results
                WHERE phase_id = p.id
                ORDER BY calculated_at DESC
                LIMIT 1
            ) s ON TRUE
            WHERE p.project_id = :project_id
            ORDER BY p.sequence ASC
            """
        ),
        {"project_id": project_id},
    ).fetchall()

    phases = []
    for row in rows:
        phases.append(
            {
                "phase_id": row[0],
                "sequence": row[1],
                "phase_group": row[2],
                "sub_phase": row[3],
                "planned_start": row[4].isoformat() if row[4] else None,
                "planned_end": row[5].isoformat() if row[5] else None,
                "planned_duration_days": row[6],
                "latest_spi": (
                    {
                        "spi_id": row[7],
                        "spi_value": row[8],
                        "alert_level": row[9],
                        "calculated_at": row[10].isoformat() if row[10] else None,
                    }
                    if row[7]
                    else None
                ),
            }
        )
    return phases


def _get_latest_prediction(session, project_id: int):
    row = session.execute(
        text(
            """
            SELECT pr.id, pr.phase_id, pr.delay_risk, pr.estimated_delay_days, pr.predicted_at
            FROM predictions pr
            JOIN phases p ON p.id = pr.phase_id
            WHERE p.project_id = :project_id
            ORDER BY pr.predicted_at DESC
            LIMIT 1
            """
        ),
        {"project_id": project_id},
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
            SELECT id, prediction_id, explanation, recommendations, generated_at
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

    return {
        "recommendation_id": row[0],
        "prediction_id": row[1],
        "explanation": row[2],
        "recommendations": parsed,
        "generated_at": row[4].isoformat() if row[4] else None,
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
    rows = session.execute(
        text(
            """
            SELECT pu.id, pu.phase_id, pu.update_date, pu.planned_percent, pu.actual_percent,
                   s.spi_value, s.alert_level, pu.entered_by
            FROM progress_updates pu
            JOIN phases p ON p.id = pu.phase_id
            LEFT JOIN spi_results s ON s.update_id = pu.id
            WHERE p.project_id = :project_id
            ORDER BY pu.created_at DESC
            """
        ),
        {"project_id": project_id},
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
