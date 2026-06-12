from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from sqlalchemy import text
import os
import traceback

load_dotenv()

app = Flask(__name__)
CORS(app)

from database.db import init_db
try:
    init_db()
    print("[performance] Database initialized successfully")
except Exception as e:
    print(f"[performance] CRITICAL: Database initialization failed: {e}")
    traceback.print_exc()
    raise SystemExit(1)


@app.route("/", methods=["GET"])
def index():
    return jsonify({
        "component": "performance",
        "service": "Construction Performance Monitoring and Delay Prediction",
        "status": "running",
        "version": "1.0.0"
    })


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "component": "performance",
        "database": "connected",
        "port": 5004
    })


@app.route("/project", methods=["POST"])
def create_project():
    data = request.get_json()
    name          = data.get("name")
    district      = data.get("district")
    province      = data.get("province")
    floors        = data.get("floors")
    building_type = data.get("building_type")
    start_date    = data.get("start_date")

    from database.db import get_db_session
    session = get_db_session()
    try:
        from database.db import Project
        project = Project(
            name=name,
            district=district,
            province=province,
            floors=floors,
            building_type=building_type,
            start_date=start_date
        )
        session.add(project)
        session.commit()
        new_project_id = project.id
        return jsonify({
            "success":    True,
            "project_id": new_project_id,
            "message":    "Project created successfully"
        })
    except Exception as e:
        session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        session.close()


@app.route("/project/<int:project_id>/phases", methods=["POST"])
def add_phases(project_id):
    phases_data = request.get_json()

    from database.db import get_db_session
    session = get_db_session()
    try:
        from database.db import Phase
        created = []
        for p in phases_data:
            phase = Phase(
                project_id=project_id,
                phase_group=p.get("phase_group"),
                phase_name=p.get("phase_name"),
                planned_start=p.get("planned_start"),
                planned_end=p.get("planned_end"),
                planned_duration_days=p.get("planned_duration_days")
            )
            session.add(phase)
            session.flush()
            created.append({
                "phase_id":   phase.id,
                "phase_group": phase.phase_group,
                "phase_name": phase.phase_name
            })
        session.commit()
        return jsonify({
            "success":        True,
            "phases_created": len(created),
            "phases":         created,
            "message":        "Phases added successfully"
        })
    except Exception as e:
        session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        session.close()


@app.route("/progress", methods=["POST"])
def record_progress():
    data = request.get_json()
    phase_id             = data.get("phase_id")
    planned_percent      = data.get("planned_percent")
    actual_percent       = data.get("actual_percent")
    actual_days_used     = data.get("actual_days_used")
    labour_availability  = data.get("labour_availability")
    material_supply      = data.get("material_supply")
    weather_severity     = data.get("weather_severity")
    entered_by           = data.get("entered_by")

    from database.db import get_db_session
    session = get_db_session()
    try:
        # ── Step 1: Save progress update ────────────────────────────────────
        from database.db import ProgressUpdate
        update = ProgressUpdate(
            phase_id=phase_id,
            planned_percent=planned_percent,
            actual_percent=actual_percent,
            actual_days_used=actual_days_used,
            labour_availability=labour_availability,
            material_supply=material_supply,
            weather_severity=weather_severity,
            entered_by=entered_by
        )
        session.add(update)
        session.flush()   # flush now so update.id is available below

        # ── Step 2: Calculate SPI (used ONLY as a trigger — not an ML input) ─
        from pipeline.spi_calculator import calculate_spi, get_alert_level
        spi_value   = calculate_spi(planned_percent or 0, actual_percent or 0)
        alert_level = get_alert_level(spi_value)

        # ── Step 3: Save SPI result, capture returned id ────────────────────
        spi_row = session.execute(text("""
            INSERT INTO spi_results (phase_id, update_id, spi_value, alert_level)
            VALUES (:phase_id, :update_id, :spi_value, :alert_level)
            RETURNING id
        """), {
            "phase_id":    phase_id,
            "update_id":   update.id,
            "spi_value":   spi_value,
            "alert_level": alert_level,
        }).fetchone()
        spi_id = spi_row[0] if spi_row else None

        # ── Step 4: Resolve phase/project context from DB ───────────────────
        phase_row = session.execute(
            text("SELECT project_id, phase_group, phase_name FROM phases WHERE id = :pid"),
            {"pid": phase_id}
        ).fetchone()
        project_id_resolved = phase_row[0] if phase_row else None
        phase_group_val     = phase_row[1] if phase_row else "Foundations"
        phase_name          = phase_row[2] if phase_row else "Foundation work"

        project_row = session.execute(
            text("SELECT district, province, floors FROM projects WHERE id = :pid"),
            {"pid": project_id_resolved}
        ).fetchone()
        district_val = project_row[0] if project_row else "Colombo"
        province_val = project_row[1] if project_row else "Northern Province"
        floors_val   = project_row[2] if project_row else 1

        # ── Step 5: Save alert ───────────────────────────────────────────────
        alert_message = (
            f"SPI = {spi_value} — schedule is on track."
            if alert_level == "NORMAL"
            else f"SPI = {spi_value} — schedule is "
                 f"{'slightly' if alert_level == 'WARNING' else 'significantly'} behind plan."
        )
        session.execute(text("""
            INSERT INTO alerts (project_id, phase_id, alert_type, message)
            VALUES (:project_id, :phase_id, :alert_type, :message)
        """), {
            "project_id": project_id_resolved,
            "phase_id":   phase_id,
            "alert_type": alert_level,
            "message":    alert_message,
        })
        session.commit()

        # ── Step 6: NORMAL — stop here, no ML needed ────────────────────────
        if alert_level == "NORMAL":
            return jsonify({
                "success":         True,
                "spi_value":       spi_value,
                "alert_level":     alert_level,
                "alert_message":   alert_message,
                "prediction":      None,
                "similar_cases":   None,
                "recommendations": None,
                "message":         "Progress recorded. SPI is healthy — no delay prediction triggered."
            })

        # ── Step 7: WARNING / CRITICAL — run ML prediction ──────────────────
        from pipeline.delay_model import predict as ml_predict
        ml_result = ml_predict(
            phase_group         = phase_group_val,
            sub_phase           = phase_name,
            district            = district_val,
            province            = province_val,
            floors              = floors_val,
            delay_category      = data.get("delay_category"),
            labour_availability = labour_availability,
            material_supply     = material_supply,
            weather_severity    = weather_severity,
            cumulative_delay    = actual_days_used or 0,
        )

        # ── Step 8: Save prediction linked to spi_id ────────────────────────
        session.execute(text("""
            INSERT INTO predictions (phase_id, spi_id, delay_risk, estimated_delay_days)
            VALUES (:phase_id, :spi_id, :delay_risk, :estimated_delay_days)
        """), {
            "phase_id":             phase_id,
            "spi_id":               spi_id,
            "delay_risk":           ml_result["risk_level"],
            "estimated_delay_days": ml_result["delay_days"],
        })
        session.commit()

        # ── Step 9: RAG — retrieve 3 similar historical cases ───────────────
        from rag.rag_pipeline import retrieve_similar_cases
        similar_cases = retrieve_similar_cases(
            phase_group = phase_group_val,
            sub_phase   = phase_name,
            district    = district_val,
            province    = province_val,
            delay_risk  = ml_result["risk_level"],
            delay_days  = ml_result["delay_days"],
            top_k       = 3,
        )

        # ── Step 10: Gemini recommendations ─────────────────────────────────
        from llm.gemini_client import generate_recommendations
        recommendations = generate_recommendations(
            phase_group   = phase_group_val,
            sub_phase     = phase_name,
            district      = district_val,
            province      = province_val,
            alert_level   = alert_level,
            delay_risk    = ml_result["risk_level"],
            delay_days    = ml_result["delay_days"],
            similar_cases = similar_cases,
        )

        return jsonify({
            "success":       True,
            "spi_value":     spi_value,
            "alert_level":   alert_level,
            "alert_message": alert_message,
            "prediction": {
                "delay_risk":           ml_result["risk_level"],
                "estimated_delay_days": ml_result["delay_days"],
                "confidence":           ml_result["confidence"],
                "risk_probabilities":   ml_result["risk_probabilities"],
            },
            "similar_cases":   similar_cases,
            "recommendations": recommendations,
            "message": (
                f"Progress recorded. {alert_level} alert triggered. "
                "ML prediction and RAG retrieval complete."
            )
        })

    except Exception as e:
        session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        session.close()


@app.route("/predict", methods=["POST"])
def predict_delay():
    data = request.get_json()

    required = ["phase_group", "sub_phase", "district", "province", "floors"]
    missing  = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({"success": False, "error": f"Missing required fields: {missing}"}), 400

    try:
        from pipeline.delay_model import predict as ml_predict

        result = ml_predict(
            phase_group         = data["phase_group"],
            sub_phase           = data["sub_phase"],
            district            = data["district"],
            province            = data["province"],
            floors              = data["floors"],
            delay_category      = data.get("delay_category"),
            labour_availability = data.get("labour_availability"),
            material_supply     = data.get("material_supply"),
            weather_severity    = data.get("weather_severity"),
            cumulative_delay    = data.get("cumulative_delay"),
        )

        # RAG: retrieve top-3 similar historical cases
        from rag.rag_pipeline import retrieve_similar_cases

        similar_cases = retrieve_similar_cases(
            phase_group = data["phase_group"],
            sub_phase   = data["sub_phase"],
            district    = data["district"],
            province    = data["province"],
            delay_risk  = result["risk_level"],
            delay_days  = result["delay_days"],
            top_k       = 3,
        )

        # Gemini recommendations
        from llm.gemini_client import generate_recommendations
        recommendations = generate_recommendations(
            phase_group   = data["phase_group"],
            sub_phase     = data["sub_phase"],
            district      = data["district"],
            province      = data["province"],
            alert_level   = result["risk_level"],
            delay_risk    = result["risk_level"],
            delay_days    = result["delay_days"],
            similar_cases = similar_cases,
        )

        return jsonify({
            "input_summary": {
                "phase_group": data["phase_group"],
                "sub_phase":   data["sub_phase"],
                "district":    data["district"],
                "province":    data["province"],
                "floors":      data["floors"],
            },
            "prediction": {
                "risk_level": result["risk_level"],
                "delay_days": result["delay_days"],
            },
            "confidence": result["confidence"],
            "model_outputs": {
                "risk_probabilities": result["risk_probabilities"],
            },
            "similar_cases":   similar_cases,
            "recommendations": recommendations,
        })

    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/project/<int:project_id>/dashboard", methods=["GET"])
def get_dashboard(project_id):
    return jsonify({
        "project": {},
        "phases": [],
        "spi_results": [],
        "predictions": [],
        "alerts": [],
        "message": "Dashboard data coming in Phase 6"
    })


@app.route("/project/<int:project_id>/alerts", methods=["GET"])
def get_alerts(project_id):
    return jsonify({
        "project_id": project_id,
        "alerts": [],
        "total": 0
    })


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5004))
    app.run(host="0.0.0.0", port=port, debug=True, use_reloader=False)
