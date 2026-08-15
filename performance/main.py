from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from sqlalchemy import text
from datetime import datetime
import json
import os
import requests
import traceback

from database.db import init_db, get_db_session, Project, Phase
from pipeline.spi_calculator import calculate_spi_from_schedule
from pipeline.feature_engineer import (
    LABOUR_MAP,
    MATERIAL_MAP,
    WEATHER_MAP,
    merge_db_context_with_assessment,
)
from pipeline.delay_model import predict_from_context, _load_models
from rag.rag_pipeline import retrieve_similar_cases
from llm.gemini_client import generate_recommendations
from monitoring.dashboard_feed import build_project_dashboard

load_dotenv()

app = Flask(__name__)
CORS(app)

try:
    init_db()
    print("[performance] Database initialized successfully")
except Exception as e:
    print(f"[performance] CRITICAL: Database initialization failed: {e}")
    traceback.print_exc()
    raise SystemExit(1)


DELAY_CATEGORY_OPTIONS = [
    "Labour",
    "Material Supply & Quality",
    "Environmental & Site",
    "Financial & Funding",
    "Design & Technical",
    "Land & Legal",
    "Owner / Social / Behavioural",
]

_ENCODER_VALUES_CACHE = {}


def _get_allowed_encoder_values(field_name: str):
    if field_name not in _ENCODER_VALUES_CACHE:
        _, _, encoders = _load_models()
        if field_name not in encoders:
            raise ValueError(f"Encoder for field '{field_name}' not found.")
        _ENCODER_VALUES_CACHE[field_name] = set(encoders[field_name].classes_.tolist())
    return _ENCODER_VALUES_CACHE[field_name]


def _require_json(req):
    data = req.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValueError("Request body must be a JSON object.")
    return data


def _error(message: str, details=None, status: int = 400):
    payload = {"success": False, "error": message}
    if details:
        payload["details"] = details
    return jsonify(payload), status


def _validate_schedule_payload(data: dict):
    errors = []
    project = data.get("project")
    phases = data.get("phases")
    if not isinstance(project, dict):
        errors.append("project must be an object.")
    if not isinstance(phases, list) or not phases:
        errors.append("phases must be a non-empty array.")
        return errors

    for key in ["name", "district", "province", "building_type"]:
        if not project or not str(project.get(key, "")).strip():
            errors.append(f"project.{key} is required.")

    floors = project.get("floors") if project else None
    try:
        floors = int(floors)
        if floors < 1 or floors > 3:
            errors.append("project.floors must be between 1 and 3.")
    except (TypeError, ValueError):
        errors.append("project.floors must be an integer.")

    seen_sequences = set()
    allowed_phase_groups = _get_allowed_encoder_values("phase_group")
    for i, phase in enumerate(phases):
        prefix = f"phases[{i}]"
        required = [
            "phase_group",
            "sub_phase",
            "planned_start",
            "planned_end",
            "planned_duration_days",
            "sequence",
        ]
        for field in required:
            if phase.get(field) in (None, ""):
                errors.append(f"{prefix}.{field} is required.")
        if phase.get("phase_group") not in allowed_phase_groups:
            errors.append(
                f"{prefix}.phase_group '{phase.get('phase_group')}' is not supported by the model."
            )
        try:
            start = datetime.strptime(phase["planned_start"], "%Y-%m-%d").date()
            end = datetime.strptime(phase["planned_end"], "%Y-%m-%d").date()
            if end < start:
                errors.append(f"{prefix}.planned_end must be >= planned_start.")
        except Exception:
            errors.append(f"{prefix}.planned_start and planned_end must be YYYY-MM-DD.")

        try:
            duration = int(phase["planned_duration_days"])
            if duration <= 0:
                errors.append(f"{prefix}.planned_duration_days must be > 0.")
        except Exception:
            errors.append(f"{prefix}.planned_duration_days must be integer.")

        try:
            sequence = int(phase["sequence"])
            if sequence in seen_sequences:
                errors.append(f"{prefix}.sequence duplicates an existing phase sequence.")
            seen_sequences.add(sequence)
        except Exception:
            errors.append(f"{prefix}.sequence must be integer.")

    return errors


def _validate_progress_spi_payload(data: dict):
    errors = []
    if data.get("phase_id") is None:
        errors.append("phase_id is required.")
    if data.get("actual_percent") is None:
        errors.append("actual_percent is required.")
    try:
        actual_percent = float(data.get("actual_percent"))
        if actual_percent < 0 or actual_percent > 100:
            errors.append("actual_percent must be between 0 and 100.")
    except (TypeError, ValueError):
        errors.append("actual_percent must be numeric.")
    try:
        int(data.get("phase_id"))
    except (TypeError, ValueError):
        errors.append("phase_id must be an integer.")
    return errors


def _validate_progress_predict_payload(data: dict):
    errors = []
    required = [
        "spi_id",
        "phase_id",
        "delay_category",
        "labour_availability",
        "material_supply",
        "weather_severity",
    ]
    for field in required:
        if data.get(field) in (None, ""):
            errors.append(f"{field} is required.")

    for field in ["spi_id", "phase_id"]:
        try:
            int(data.get(field))
        except (TypeError, ValueError):
            errors.append(f"{field} must be an integer.")

    if data.get("delay_category") not in DELAY_CATEGORY_OPTIONS:
        errors.append("delay_category is invalid.")
    if data.get("labour_availability") not in LABOUR_MAP:
        errors.append("labour_availability is invalid.")
    if data.get("material_supply") not in MATERIAL_MAP:
        errors.append("material_supply is invalid.")
    if data.get("weather_severity") not in WEATHER_MAP:
        errors.append("weather_severity is invalid.")
    return errors


def _get_phase_context(session, phase_id: int):
    row = session.execute(
        text(
            """
            SELECT p.id, p.project_id, p.phase_group, p.sub_phase,
                   p.planned_start, p.planned_end, p.sequence,
                   pr.district, pr.province, pr.floors
            FROM phases p
            JOIN projects pr ON pr.id = p.project_id
            WHERE p.id = :phase_id
            """
        ),
        {"phase_id": phase_id},
    ).fetchone()
    return row


def _get_spi_context(session, spi_id: int, phase_id: int):
    row = session.execute(
        text(
            """
            SELECT s.id, s.alert_level, s.update_id,
                   p.id, p.project_id, p.phase_group, p.sub_phase, p.sequence,
                   pr.district, pr.province, pr.floors
            FROM spi_results s
            JOIN phases p ON p.id = s.phase_id
            JOIN projects pr ON pr.id = p.project_id
            WHERE s.id = :spi_id
              AND p.id = :phase_id
            """
        ),
        {"spi_id": spi_id, "phase_id": phase_id},
    ).fetchone()
    return row


def _compute_cumulative_delay_days(session, project_id: int, current_phase_sequence: int) -> int:
    row = session.execute(
        text(
            """
            SELECT COALESCE(SUM(latest_delay), 0) AS cumulative
            FROM (
                SELECT ph.id,
                       COALESCE(
                         (
                           SELECT pr.estimated_delay_days
                           FROM predictions pr
                           WHERE pr.phase_id = ph.id
                           ORDER BY pr.predicted_at DESC
                           LIMIT 1
                         ), 0
                       ) AS latest_delay
                FROM phases ph
                WHERE ph.project_id = :project_id
                  AND ph.sequence < :phase_sequence
            ) prior
            """
        ),
        {"project_id": project_id, "phase_sequence": current_phase_sequence},
    ).fetchone()
    return int(round(float(row[0]))) if row and row[0] is not None else 0


def _notify_if_high_risk(project_id: int, phase: str, delay_days: int, delay_risk: str) -> dict:
    status = {"sent_to_c02": False, "sent_to_c03": False, "errors": []}
    if delay_risk != "HIGH":
        return status

    c02_url = os.getenv("C02_NOTIFY_URL", "http://cost-estimation:5002/delay-alert")
    c03_url = os.getenv("C03_NOTIFY_URL", "http://timeline:5003/delay-alert")
    timeout = float(os.getenv("NOTIFY_TIMEOUT_SECONDS", "5"))
    payload = {
        "project_id": project_id,
        "phase": phase,
        "delay_days": delay_days,
    }

    for target, key in [(c02_url, "sent_to_c02"), (c03_url, "sent_to_c03")]:
        try:
            resp = requests.post(target, json=payload, timeout=timeout)
            if 200 <= resp.status_code < 300:
                status[key] = True
            else:
                status["errors"].append(f"{target} returned status {resp.status_code}")
        except Exception as exc:
            status["errors"].append(f"{target} failed: {exc}")
    return status


@app.route("/", methods=["GET"])
def index():
    return jsonify(
        {
            "component": "performance",
            "service": "Construction Performance Monitoring and Delay Prediction",
            "status": "running",
            "version": "2.0.0",
            "endpoints": [
                "POST /schedule",
                "POST /progress/spi",
                "POST /progress/predict",
                "GET /project/<id>/dashboard",
            ],
        }
    )


@app.route("/health", methods=["GET"])
def health():
    try:
        session = get_db_session()
        session.execute(text("SELECT 1"))
        session.close()
        db_status = "connected"
    except Exception:
        db_status = "unavailable"
    return jsonify(
        {
            "status": "ok" if db_status == "connected" else "degraded",
            "component": "performance",
            "database": db_status,
            "port": 5004,
        }
    )


@app.route("/schedule", methods=["POST"])
def post_schedule():
    try:
        data = _require_json(request)
    except ValueError as exc:
        return _error(str(exc), status=400)

    validation_errors = _validate_schedule_payload(data)
    if validation_errors:
        return _error("Validation failed", details=validation_errors, status=400)

    project = data["project"]
    phases = sorted(data["phases"], key=lambda p: int(p["sequence"]))

    session = get_db_session()
    try:
        project_row = Project(
            name=project["name"].strip(),
            district=project["district"].strip(),
            province=project["province"].strip(),
            floors=int(project["floors"]),
            building_type=project["building_type"].strip(),
        )
        session.add(project_row)
        session.flush()

        created_phase_ids = []
        for phase in phases:
            phase_row = Phase(
                project_id=project_row.id,
                phase_group=phase["phase_group"],
                sub_phase=phase["sub_phase"],
                planned_start=phase["planned_start"],
                planned_end=phase["planned_end"],
                planned_duration_days=int(phase["planned_duration_days"]),
                sequence=int(phase["sequence"]),
            )
            session.add(phase_row)
            session.flush()
            created_phase_ids.append(phase_row.id)

        session.commit()
        return (
            jsonify(
                {
                    "success": True,
                    "project_id": project_row.id,
                    "phases_created": len(created_phase_ids),
                    "phase_ids": created_phase_ids,
                    "message": "Schedule baseline saved successfully.",
                }
            ),
            201,
        )
    except Exception as exc:
        session.rollback()
        return _error("Failed to save schedule baseline.", details=[str(exc)], status=500)
    finally:
        session.close()


@app.route("/progress/spi", methods=["POST"])
def post_progress_spi():
    try:
        data = _require_json(request)
    except ValueError as exc:
        return _error(str(exc), status=400)

    validation_errors = _validate_progress_spi_payload(data)
    if validation_errors:
        return _error("Validation failed", details=validation_errors, status=400)

    phase_id = int(data["phase_id"])
    actual_percent = float(data["actual_percent"])
    entered_by = data.get("entered_by")

    session = get_db_session()
    try:
        phase_context = _get_phase_context(session, phase_id)
        if not phase_context:
            return _error(f"Invalid phase_id: {phase_id}. Phase not found.", status=404)

        (
            _phase_id,
            project_id,
            _phase_group,
            _sub_phase,
            planned_start,
            planned_end,
            _sequence,
            _district,
            _province,
            _floors,
        ) = phase_context

        spi_result = calculate_spi_from_schedule(
            planned_start=planned_start,
            planned_end=planned_end,
            actual_percent=actual_percent,
        )

        progress_row = session.execute(
            text(
                """
                INSERT INTO progress_updates (
                    phase_id, planned_percent, actual_percent, entered_by
                ) VALUES (
                    :phase_id, :planned_percent, :actual_percent, :entered_by
                )
                RETURNING id
                """
            ),
            {
                "phase_id": phase_id,
                "planned_percent": spi_result["planned_percent"],
                "actual_percent": spi_result["actual_percent"],
                "entered_by": entered_by,
            },
        ).fetchone()
        progress_update_id = progress_row[0]

        spi_row = session.execute(
            text(
                """
                INSERT INTO spi_results (phase_id, update_id, spi_value, alert_level)
                VALUES (:phase_id, :update_id, :spi_value, :alert_level)
                RETURNING id
                """
            ),
            {
                "phase_id": phase_id,
                "update_id": progress_update_id,
                "spi_value": spi_result["spi_value"],
                "alert_level": spi_result["alert_level"],
            },
        ).fetchone()
        spi_id = spi_row[0]

        if spi_result["alert_level"] in ("WARNING", "CRITICAL"):
            message = (
                f"SPI = {spi_result['spi_value']} - schedule is slightly behind plan."
                if spi_result["alert_level"] == "WARNING"
                else f"SPI = {spi_result['spi_value']} - schedule is significantly behind plan."
            )
            session.execute(
                text(
                    """
                    INSERT INTO alerts (project_id, phase_id, spi_id, alert_type, message)
                    VALUES (:project_id, :phase_id, :spi_id, :alert_type, :message)
                    """
                ),
                {
                    "project_id": project_id,
                    "phase_id": phase_id,
                    "spi_id": spi_id,
                    "alert_type": spi_result["alert_level"],
                    "message": message,
                },
            )

        session.commit()
        return jsonify(
            {
                "success": True,
                "project_id": project_id,
                "phase_id": phase_id,
                "progress_update_id": progress_update_id,
                "spi_id": spi_id,
                "planned_percent": spi_result["planned_percent"],
                "actual_percent": spi_result["actual_percent"],
                "spi_value": spi_result["spi_value"],
                "alert_level": spi_result["alert_level"],
                "requires_prediction_step": spi_result["alert_level"] in ("WARNING", "CRITICAL"),
                "message": "SPI calculated successfully.",
            }
        )
    except Exception as exc:
        session.rollback()
        return _error("Failed to process SPI progress.", details=[str(exc)], status=500)
    finally:
        session.close()


@app.route("/progress/predict", methods=["POST"])
def post_progress_predict():
    try:
        data = _require_json(request)
    except ValueError as exc:
        return _error(str(exc), status=400)

    validation_errors = _validate_progress_predict_payload(data)
    if validation_errors:
        return _error("Validation failed", details=validation_errors, status=400)

    spi_id = int(data["spi_id"])
    phase_id = int(data["phase_id"])

    session = get_db_session()
    try:
        spi_context = _get_spi_context(session, spi_id, phase_id)
        if not spi_context:
            return _error("Invalid spi_id/phase_id combination.", status=404)

        (
            _spi_id,
            alert_level,
            progress_update_id,
            _phase_id,
            project_id,
            phase_group,
            sub_phase,
            sequence,
            district,
            province,
            floors,
        ) = spi_context

        if alert_level == "NORMAL":
            return _error(
                "Prediction step is allowed only for WARNING or CRITICAL SPI.",
                status=400,
            )

        cumulative_delay = _compute_cumulative_delay_days(session, project_id, sequence)
        assessment_payload = {
            "delay_category": data["delay_category"],
            "labour_availability": data["labour_availability"],
            "material_supply": data["material_supply"],
            "weather_severity": data["weather_severity"],
        }

        assessment_row = session.execute(
            text(
                """
                INSERT INTO delay_assessments (
                    project_id, phase_id, spi_id, progress_update_id,
                    delay_category,
                    labour_availability_label, labour_availability_score,
                    material_supply_label, material_supply_score,
                    weather_severity_label, weather_severity_score
                ) VALUES (
                    :project_id, :phase_id, :spi_id, :progress_update_id,
                    :delay_category,
                    :labour_availability_label, :labour_availability_score,
                    :material_supply_label, :material_supply_score,
                    :weather_severity_label, :weather_severity_score
                )
                RETURNING id
                """
            ),
            {
                "project_id": project_id,
                "phase_id": phase_id,
                "spi_id": spi_id,
                "progress_update_id": progress_update_id,
                "delay_category": assessment_payload["delay_category"],
                "labour_availability_label": assessment_payload["labour_availability"],
                "labour_availability_score": LABOUR_MAP[assessment_payload["labour_availability"]],
                "material_supply_label": assessment_payload["material_supply"],
                "material_supply_score": MATERIAL_MAP[assessment_payload["material_supply"]],
                "weather_severity_label": assessment_payload["weather_severity"],
                "weather_severity_score": WEATHER_MAP[assessment_payload["weather_severity"]],
            },
        ).fetchone()
        assessment_id = assessment_row[0]

        db_context = {
            "phase_group": phase_group,
            "sub_phase": sub_phase,
            "district": district,
            "province": province,
            "floors": floors,
        }
        features_context = merge_db_context_with_assessment(
            db_context=db_context,
            assessment_payload=assessment_payload,
            cumulative_delay=cumulative_delay,
        )
        ml_result = predict_from_context(features_context)

        prediction_row = session.execute(
            text(
                """
                INSERT INTO predictions (
                    phase_id, spi_id, assessment_id, delay_risk, estimated_delay_days, cumulative_delay_days
                )
                VALUES (
                    :phase_id, :spi_id, :assessment_id, :delay_risk, :estimated_delay_days, :cumulative_delay_days
                )
                RETURNING id
                """
            ),
            {
                "phase_id": phase_id,
                "spi_id": spi_id,
                "assessment_id": assessment_id,
                "delay_risk": ml_result["risk_level"],
                "estimated_delay_days": ml_result["delay_days"],
                "cumulative_delay_days": cumulative_delay,
            },
        ).fetchone()
        prediction_id = prediction_row[0]

        similar_cases = retrieve_similar_cases(
            district=district,
            phase_group=phase_group,
            delay_category=assessment_payload["delay_category"],
            top_k=3,
        )
        recommendations = generate_recommendations(
            phase_group=phase_group,
            sub_phase=sub_phase,
            district=district,
            province=province,
            spi_alert=alert_level,
            delay_risk=ml_result["risk_level"],
            delay_days=ml_result["delay_days"],
            similar_cases=similar_cases,
        )

        recommendation_row = session.execute(
            text(
                """
                INSERT INTO recommendations (
                    prediction_id, explanation, recommendations, similar_cases_used, generated_at
                ) VALUES (
                    :prediction_id, :explanation, :recommendations, :similar_cases_used, CURRENT_TIMESTAMP
                )
                RETURNING id
                """
            ),
            {
                "prediction_id": prediction_id,
                "explanation": recommendations.get("explanation"),
                "recommendations": json.dumps(
                    recommendations.get("corrective_actions", []), ensure_ascii=False
                ),
                "similar_cases_used": json.dumps(similar_cases, ensure_ascii=False),
            },
        ).fetchone()
        recommendation_id = recommendation_row[0]

        notify_status = _notify_if_high_risk(
            project_id=project_id,
            phase=f"{phase_group} / {sub_phase}",
            delay_days=ml_result["delay_days"],
            delay_risk=ml_result["risk_level"],
        )

        session.commit()
        return jsonify(
            {
                "success": True,
                "project_id": project_id,
                "phase_id": phase_id,
                "spi_id": spi_id,
                "alert_level": alert_level,
                "prediction_id": prediction_id,
                "prediction": {
                    "delay_risk": ml_result["risk_level"],
                    "estimated_delay_days": ml_result["delay_days"],
                    "confidence": ml_result["confidence"],
                    "risk_probabilities": ml_result["risk_probabilities"],
                },
                "similar_cases": similar_cases,
                "recommendation_id": recommendation_id,
                "recommendation": {
                    "explanation": recommendations.get("explanation"),
                    "corrective_actions": recommendations.get("corrective_actions"),
                },
                "notifications": {
                    "sent_to_c02": notify_status["sent_to_c02"],
                    "sent_to_c03": notify_status["sent_to_c03"],
                    "errors": notify_status["errors"],
                },
                "message": "Prediction, retrieval, recommendation, and notifications completed.",
            }
        )
    except Exception as exc:
        session.rollback()
        return _error("Failed to run prediction flow.", details=[str(exc)], status=500)
    finally:
        session.close()


@app.route("/project", methods=["POST"])
def deprecated_create_project():
    return (
        jsonify(
            {
                "success": False,
                "error": "Deprecated endpoint. Use POST /schedule instead.",
            }
        ),
        410,
    )


@app.route("/project/<int:project_id>/phases", methods=["POST"])
def deprecated_add_phases(project_id):
    return (
        jsonify(
            {
                "success": False,
                "error": "Deprecated endpoint. Use POST /schedule instead.",
                "project_id": project_id,
            }
        ),
        410,
    )


@app.route("/progress", methods=["POST"])
def deprecated_progress():
    return (
        jsonify(
            {
                "success": False,
                "error": "Deprecated endpoint. Use POST /progress/spi then POST /progress/predict.",
            }
        ),
        410,
    )


@app.route("/predict", methods=["POST"])
def deprecated_predict():
    return (
        jsonify(
            {
                "success": False,
                "error": "Deprecated endpoint. Use POST /progress/predict.",
            }
        ),
        410,
    )


@app.route("/project/<int:project_id>/dashboard", methods=["GET"])
def get_dashboard(project_id):
    payload = build_project_dashboard(project_id)
    if not payload.get("success"):
        return jsonify(payload), 404
    return jsonify(payload)


@app.route("/project/<int:project_id>/alerts", methods=["GET"])
def get_alerts(project_id):
    active_only = request.args.get("active_only", "true").lower() == "true"
    session = get_db_session()
    try:
        if active_only:
            rows = session.execute(
                text(
                    """
                    SELECT id, phase_id, spi_id, alert_type, message, created_at
                    FROM alerts
                    WHERE project_id = :project_id
                      AND COALESCE(is_resolved, FALSE) = FALSE
                    ORDER BY created_at DESC
                    """
                ),
                {"project_id": project_id},
            ).fetchall()
        else:
            rows = session.execute(
                text(
                    """
                    SELECT id, phase_id, spi_id, alert_type, message, created_at
                    FROM alerts
                    WHERE project_id = :project_id
                    ORDER BY created_at DESC
                    """
                ),
                {"project_id": project_id},
            ).fetchall()

        alerts = [
            {
                "alert_id": row[0],
                "phase_id": row[1],
                "spi_id": row[2],
                "alert_type": row[3],
                "message": row[4],
                "created_at": row[5].isoformat() if row[5] else None,
            }
            for row in rows
        ]
        return jsonify(
            {
                "success": True,
                "project_id": project_id,
                "alerts": alerts,
                "total": len(alerts),
                "active_only": active_only,
            }
        )
    except Exception as exc:
        return _error("Failed to retrieve alerts.", details=[str(exc)], status=500)
    finally:
        session.close()


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5004))
    app.run(host="0.0.0.0", port=port, debug=True, use_reloader=False)
