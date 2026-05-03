from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import os

load_dotenv()

app = Flask(__name__)
CORS(app)

from database.db import init_db
try:
    init_db()
    print("[performance] Database initialized successfully.")
except Exception as e:
    print(f"[performance] Database initialization failed: {e}")


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
    name = data.get("name")
    district = data.get("district")
    floors = data.get("floors")
    building_type = data.get("building_type")
    start_date = data.get("start_date")

    from database.db import get_db_session
    session = get_db_session()
    try:
        from database.db import Project
        project = Project(
            name=name,
            district=district,
            floors=floors,
            building_type=building_type,
            start_date=start_date
        )
        session.add(project)
        session.commit()
        new_project_id = project.id
        return jsonify({
            "success": True,
            "project_id": new_project_id,
            "message": "Project created successfully"
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
        count = 0
        for p in phases_data:
            phase = Phase(
                project_id=project_id,
                phase_name=p.get("phase_name"),
                planned_start=p.get("planned_start"),
                planned_end=p.get("planned_end"),
                planned_duration_days=p.get("planned_duration_days")
            )
            session.add(phase)
            count += 1
        session.commit()
        return jsonify({
            "success": True,
            "phases_created": count,
            "message": "Phases added successfully"
        })
    except Exception as e:
        session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        session.close()


@app.route("/progress", methods=["POST"])
def record_progress():
    data = request.get_json()
    phase_id = data.get("phase_id")
    planned_percent = data.get("planned_percent")
    actual_percent = data.get("actual_percent")
    actual_days_used = data.get("actual_days_used")
    labour_availability = data.get("labour_availability")
    material_supply_status = data.get("material_supply_status")
    weather_severity = data.get("weather_severity")
    entered_by = data.get("entered_by")

    from database.db import get_db_session
    session = get_db_session()
    try:
        from database.db import ProgressUpdate
        update = ProgressUpdate(
            phase_id=phase_id,
            planned_percent=planned_percent,
            actual_percent=actual_percent,
            actual_days_used=actual_days_used,
            labour_availability=labour_availability,
            material_supply_status=material_supply_status,
            weather_severity=weather_severity,
            entered_by=entered_by
        )
        session.add(update)
        session.commit()

        # TODO Phase 2: calculate SPI here
        # TODO Phase 3: run ML prediction here

        return jsonify({
            "success": True,
            "spi_value": 0.0,
            "alert_level": "PENDING",
            "delay_risk": "PENDING",
            "estimated_delay_days": 0,
            "message": "Progress recorded. SPI and prediction coming in Phase 2 and 3"
        })
    except Exception as e:
        session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        session.close()


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
    app.run(host="0.0.0.0", port=port, debug=True)
