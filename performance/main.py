from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from sqlalchemy import text
from datetime import datetime
import json
import os
import requests
import traceback

from database.db import init_db, get_db_session
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
from weather.weather_client import get_current_weather, resolve_weather_severity, validate_coordinates
from timeline_source import get_timeline_provider

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
    """
    Client-facing error. `details` is for VALIDATION messages we author
    ourselves and are safe to expose - never raw exception text (see
    _server_error).
    """
    payload = {"success": False, "error": message}
    if details:
        payload["details"] = details
    return jsonify(payload), status


def _server_error(message: str, exc: Exception, status: int = 500):
    """
    Unexpected server-side failure. The full exception (with traceback) is
    kept server-side only; the client gets a generic, safe message.

    Previously these handlers returned details=[str(exc)], which leaked DB
    error text, table/column names and internal service URLs to any caller -
    and fed unescaped straight into the frontend. Same reasoning as
    weather/weather_client.py:_safe_error_message.
    """
    traceback.print_exc()
    print(f"[performance] ERROR: {message}: {type(exc).__name__}: {exc}")
    return jsonify({"success": False, "error": message}), status


# Column widths from database/db.py - validated here so oversized input
# returns a clean 400 instead of hitting Postgres and surfacing as a 500.
MAX_LENGTHS = {
    "project.name": 255,
    "project.district": 100,
    "project.province": 100,
    "project.building_type": 100,
    "phase.phase_group": 100,
    "phase.sub_phase": 100,
    "entered_by": 100,
}


def _check_length(errors: list, field_label: str, value, max_key: str = None):
    limit = MAX_LENGTHS[max_key or field_label]
    if value is not None and len(str(value)) > limit:
        errors.append(f"{field_label} must be at most {limit} characters.")


def _validate_schedule_payload(data: dict):
    errors = []
    project = data.get("project")
    phases = data.get("phases")
    if not isinstance(project, dict):
        # Audit fix: a non-dict project (string, list, int, ...) used to
        # crash with an uncaught AttributeError the moment project.get(...)
        # was called below, producing a raw 500 instead of a clean
        # validation error - same bug class already fixed for phases[i]
        # below. Substituting an empty dict lets every existing
        # project.get(...) call downstream behave exactly as if all fields
        # were simply missing, so this degrades into normal
        # "project.X is required" errors instead of crashing.
        errors.append("project must be an object.")
        project = {}
    if not isinstance(phases, list) or not phases:
        errors.append("phases must be a non-empty array.")
        return errors

    for key in ["name", "district", "province", "building_type"]:
        if not project or not str(project.get(key, "")).strip():
            errors.append(f"project.{key} is required.")
        else:
            _check_length(errors, f"project.{key}", project.get(key))

    floors = project.get("floors") if project else None
    try:
        floors = int(floors)
        if floors < 1 or floors > 3:
            errors.append("project.floors must be between 1 and 3.")
    except (TypeError, ValueError):
        errors.append("project.floors must be an integer.")

    # Site coordinates (map-based location picker) are optional. If given,
    # both latitude and longitude must be present and within valid ranges -
    # see weather.weather_client.validate_coordinates.
    if project:
        errors.extend(validate_coordinates(project.get("latitude"), project.get("longitude")))

    seen_sequences = set()
    allowed_phase_groups = _get_allowed_encoder_values("phase_group")
    for i, phase in enumerate(phases):
        prefix = f"phases[{i}]"
        if not isinstance(phase, dict):
            # Audit fix: a malformed entry here (null, string, list, ...)
            # used to raise an uncaught AttributeError on phase.get(...)
            # below, producing a raw 500 instead of a clean validation error.
            errors.append(f"{prefix} must be an object.")
            continue
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
        _check_length(errors, f"{prefix}.phase_group", phase.get("phase_group"), "phase.phase_group")
        _check_length(errors, f"{prefix}.sub_phase", phase.get("sub_phase"), "phase.sub_phase")
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
    _check_length(errors, "entered_by", data.get("entered_by"))
    return errors


def _validate_progress_predict_payload(data: dict):
    """
    NOTE (Phase 2 - weather integration): weather_severity is now OPTIONAL.
    The house-owner-facing workflow fetches weather automatically server-side
    (see post_progress_predict / weather.weather_client). weather_severity is
    still accepted as an optional manual override/fallback field so existing
    callers (e.g. the Postman collection, or a client that already has a
    reading) keep working unchanged - it is only validated *if present*.
    """
    errors = []
    required = [
        "spi_id",
        "phase_id",
        "delay_category",
        "labour_availability",
        "material_supply",
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
    if data.get("weather_severity") not in (None, "") and data.get("weather_severity") not in WEATHER_MAP:
        errors.append("weather_severity is invalid.")
    return errors


def _get_phase_context(session, phase_id: int):
    """
    ARCHITECTURE NOTE: phase/project fields now come from the
    TimelineProvider interface (timeline_source/), not a direct SQL join
    against `phases`/`projects` - Performance does not own this data, see
    timeline_source/base.py. Only the SPI-specific lookup below (if any)
    would stay as direct SQL, since spi_results genuinely belongs to
    Performance.
    """
    phase = get_timeline_provider().get_phase(phase_id)
    return phase


def _get_spi_context(session, spi_id: int, phase_id: int):
    """
    Combines a Performance-owned record (spi_results - genuinely ours) with
    Timeline-owned phase/project context (via TimelineProvider, not direct
    SQL - see architecture note on _get_phase_context above).
    """
    spi_row = session.execute(
        text(
            """
            SELECT id, alert_level, update_id
            FROM spi_results
            WHERE id = :spi_id
              AND phase_id = :phase_id
            """
        ),
        {"spi_id": spi_id, "phase_id": phase_id},
    ).fetchone()
    if not spi_row:
        return None

    phase = get_timeline_provider().get_phase(phase_id)
    if not phase:
        return None

    return {
        "spi_id": spi_row[0],
        "alert_level": spi_row[1],
        "progress_update_id": spi_row[2],
        "phase_id": phase["phase_id"],
        "project_id": phase["project_id"],
        "phase_group": phase["phase_group"],
        "sub_phase": phase["sub_phase"],
        "sequence": phase["sequence"],
        "district": phase["district"],
        "province": phase["province"],
        "floors": phase["floors"],
        "latitude": phase.get("latitude"),
        "longitude": phase.get("longitude"),
    }


def _compute_cumulative_delay_days(session, project_id: int, current_phase_sequence: int) -> int:
    """
    Which phases precede this one (by sequence) is Timeline-owned schedule
    data, sourced via TimelineProvider - not a direct `phases` table query.
    The actual delay figures summed here (`predictions.estimated_delay_days`)
    are genuinely Performance-owned, so that part stays as direct SQL.
    """
    prior_phase_ids = [
        p["phase_id"]
        for p in get_timeline_provider().list_phases(project_id)
        if p["sequence"] < current_phase_sequence
    ]
    if not prior_phase_ids:
        return 0

    row = session.execute(
        text(
            """
            SELECT COALESCE(SUM(latest_delay), 0) AS cumulative
            FROM (
                SELECT ph_id,
                       COALESCE(
                         (
                           SELECT pr.estimated_delay_days
                           FROM predictions pr
                           WHERE pr.phase_id = ph_id
                           ORDER BY pr.predicted_at DESC
                           LIMIT 1
                         ), 0
                       ) AS latest_delay
                FROM unnest(:phase_ids) AS ph_id
            ) prior
            """
        ),
        {"phase_ids": prior_phase_ids},
    ).fetchone()
    return int(round(float(row[0]))) if row and row[0] is not None else 0


def _notify_if_high_risk(project_id: int, phase: str, delay_days: int, delay_risk: str) -> dict:
    status = {"sent_to_c02": False, "sent_to_c03": False, "errors": []}
    if delay_risk != "HIGH":
        return status

    # Audit fix: .env actually defines C02_URL/C03_URL (base host only, e.g.
    # "http://cost-estimation:5002"), not C02_NOTIFY_URL/C03_NOTIFY_URL - the
    # old code silently ignored .env and always fell back to the hardcoded
    # "...:5002/delay-alert" default. This now reads the real .env keys and
    # appends the expected path, falls back to the legacy *_NOTIFY_URL names
    # (already full URLs, kept for any deployment still using them), and
    # only then falls back to the fully hardcoded default.
    def _resolve_notify_url(base_env_key: str, legacy_env_key: str, default_full_url: str) -> str:
        base = os.getenv(base_env_key)
        if base:
            return base.rstrip("/") + "/delay-alert"
        return os.getenv(legacy_env_key, default_full_url)

    c02_url = _resolve_notify_url("C02_URL", "C02_NOTIFY_URL", "http://cost-estimation:5002/delay-alert")
    c03_url = _resolve_notify_url("C03_URL", "C03_NOTIFY_URL", "http://timeline:5003/delay-alert")
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
                "GET /projects",
                "POST /schedule",
                "PATCH /project/<id>/location",
                "POST /progress/spi",
                "GET /project/<id>/weather",
                "POST /progress/predict",
                "GET /project/<id>/dashboard",
                "GET /project/<id>/alerts",
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


@app.route("/projects", methods=["GET"])
def list_projects():
    """
    Phase 2 - name-based project selection. Lightweight read-only listing so
    Form 1 can show a Project dropdown by name instead of requiring a raw
    numeric project_id.

    ARCHITECTURE NOTE: sourced via the TimelineProvider interface
    (timeline_source/), not direct SQL - Performance does not own this
    data long-term (see timeline_source/base.py). Today TIMELINE_SOURCE
    defaults to the local/mock provider backed by Performance's own
    tables; this route does not need to change when that's swapped for
    the real Timeline component.
    """
    try:
        projects = get_timeline_provider().list_projects()
        return jsonify({"success": True, "projects": projects, "total": len(projects)})
    except Exception as exc:
        return _server_error("Failed to list projects.", exc)


@app.route("/project/<int:project_id>/weather", methods=["GET"])
def get_project_weather(project_id):
    """
    Phase 2 - live weather preview for Form 2. Returns the SAME server-side
    weather resolution /progress/predict uses internally (see
    weather.weather_client), so the house-owner sees exactly what will feed
    the prediction before submitting. Never returns a hard failure to the
    client - a weather-provider error still returns 200 with
    "success": false / a fallback severity, per the graceful-degradation
    requirement.

    Prefers the project's exact site coordinates (latitude/longitude) when
    set; falls back to district-name lookup for projects created before the
    map-based location picker existed.

    Project lookup goes through TimelineProvider, not direct SQL - see
    architecture note on list_projects above.
    """
    try:
        project = get_timeline_provider().get_project(project_id)
        if not project:
            return _error(f"Invalid project_id: {project_id}. Project not found.", status=404)

        weather = get_current_weather(
            district=project["district"],
            latitude=project.get("latitude"),
            longitude=project.get("longitude"),
        )
        return jsonify({"success": True, "project_id": project_id, "weather": weather})
    except Exception as exc:
        return _server_error("Failed to retrieve weather.", exc)


@app.route("/schedule", methods=["POST"])
def post_schedule():
    """
    TEMPORARY / DEV-ONLY. In the final architecture, projects/phases are
    created and owned by the Timeline component, not Performance - see
    timeline_source/base.py. This endpoint exists only so the local mock
    timeline source (TIMELINE_SOURCE=local, the default today) has a way to
    be seeded with test data. It intentionally refuses to run against
    TIMELINE_SOURCE=remote, since Performance must not create Timeline's
    data once the real component is integrated - see
    timeline_source/local_provider.py's create_project/create_phase
    docstring for why those methods live outside the TimelineProvider
    interface.
    """
    if os.getenv("TIMELINE_SOURCE", "local").strip().lower() == "remote":
        return _error(
            "POST /schedule is a temporary dev-only seeding endpoint for the "
            "local mock timeline source and is disabled when TIMELINE_SOURCE=remote. "
            "Create projects/phases via the Timeline component instead.",
            status=410,
        )
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
        mock_provider = get_timeline_provider()  # guaranteed local at this point (checked above)
        project_id = mock_provider.create_project(
            session,
            name=project["name"],
            district=project["district"],
            province=project["province"],
            floors=project["floors"],
            building_type=project["building_type"],
            latitude=project.get("latitude"),
            longitude=project.get("longitude"),
        )

        created_phase_ids = []
        for phase in phases:
            phase_id = mock_provider.create_phase(
                session,
                project_id=project_id,
                phase_group=phase["phase_group"],
                sub_phase=phase["sub_phase"],
                planned_start=phase["planned_start"],
                planned_end=phase["planned_end"],
                planned_duration_days=phase["planned_duration_days"],
                sequence=phase["sequence"],
            )
            created_phase_ids.append(phase_id)

        session.commit()
        return (
            jsonify(
                {
                    "success": True,
                    "project_id": project_id,
                    "phases_created": len(created_phase_ids),
                    "phase_ids": created_phase_ids,
                    "message": "Schedule baseline saved successfully.",
                }
            ),
            201,
        )
    except Exception as exc:
        session.rollback()
        return _server_error("Failed to save schedule baseline.", exc)
    finally:
        session.close()


@app.route("/project/<int:project_id>/location", methods=["PATCH"])
def update_project_location(project_id):
    """
    Updates an existing project's exact site coordinates (map-based location
    picker). TEMPORARY / DEV-ONLY, same reasoning as POST /schedule above -
    Timeline owns this data in the final architecture, not Performance - see
    timeline_source/local_provider.py's update_project_location docstring.
    Disabled when TIMELINE_SOURCE=remote, same as /schedule.

    Lets a house owner move the pin after the project already exists,
    instead of the site location being permanently fixed at creation time.
    Weather for the project immediately reflects the new coordinates on the
    next /project/<id>/weather or /progress/predict call - no separate
    "refresh" step needed server-side.
    """
    if os.getenv("TIMELINE_SOURCE", "local").strip().lower() == "remote":
        return _error(
            "PATCH /project/<id>/location is a temporary dev-only endpoint for the "
            "local mock timeline source and is disabled when TIMELINE_SOURCE=remote.",
            status=410,
        )
    try:
        data = _require_json(request)
    except ValueError as exc:
        return _error(str(exc), status=400)

    errors = []
    if data.get("latitude") in (None, "") or data.get("longitude") in (None, ""):
        errors.append("latitude and longitude are both required.")
    else:
        errors.extend(validate_coordinates(data.get("latitude"), data.get("longitude")))
    if errors:
        return _error("Validation failed", details=errors, status=400)

    session = get_db_session()
    try:
        provider = get_timeline_provider()
        project = provider.get_project(project_id)
        if not project:
            return _error(f"Invalid project_id: {project_id}. Project not found.", status=404)

        updated = provider.update_project_location(
            session,
            project_id=project_id,
            latitude=float(data["latitude"]),
            longitude=float(data["longitude"]),
        )
        session.commit()
        return jsonify(
            {
                "success": True,
                "project_id": project_id,
                "latitude": updated["latitude"],
                "longitude": updated["longitude"],
                "message": "Project location updated.",
            }
        )
    except Exception as exc:
        session.rollback()
        return _server_error("Failed to update project location.", exc)
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

        project_id = phase_context["project_id"]
        planned_start = phase_context["planned_start"]
        planned_end = phase_context["planned_end"]

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
        return _server_error("Failed to process SPI progress.", exc)
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

        alert_level = spi_context["alert_level"]
        progress_update_id = spi_context["progress_update_id"]
        project_id = spi_context["project_id"]
        phase_group = spi_context["phase_group"]
        sub_phase = spi_context["sub_phase"]
        sequence = spi_context["sequence"]
        district = spi_context["district"]
        province = spi_context["province"]
        floors = spi_context["floors"]
        latitude = spi_context.get("latitude")
        longitude = spi_context.get("longitude")

        if alert_level == "NORMAL":
            return _error(
                "Prediction step is allowed only for WARNING or CRITICAL SPI.",
                status=400,
            )

        cumulative_delay = _compute_cumulative_delay_days(session, project_id, sequence)

        # Phase 2 - weather integration: resolve weather_severity server-side.
        # If the client supplied a valid manual value, it's used as an
        # explicit override (no live call made). Otherwise weather is fetched
        # live for the project's exact site coordinates when available
        # (falls back to district-name lookup for projects created before
        # coordinates existed - see weather.weather_client); on any failure
        # this falls back to a safe default rather than failing the whole
        # prediction request.
        weather_result = resolve_weather_severity(
            district=district,
            latitude=latitude,
            longitude=longitude,
            manual_override=data.get("weather_severity"),
        )
        assessment_payload = {
            "delay_category": data["delay_category"],
            "labour_availability": data["labour_availability"],
            "material_supply": data["material_supply"],
            "weather_severity": weather_result["weather_severity"],
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
            delay_category=assessment_payload["delay_category"],
            labour_availability=assessment_payload["labour_availability"],
            material_supply=assessment_payload["material_supply"],
            weather_info=weather_result,
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
                "weather_used": {
                    "source": weather_result["source"],
                    "weather_severity": weather_result["weather_severity"],
                    "temperature_c": weather_result.get("temperature_c"),
                    "condition": weather_result.get("condition"),
                    "rainfall_mm": weather_result.get("rainfall_mm"),
                    "error": weather_result.get("error"),
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
        return _server_error("Failed to run prediction flow.", exc)
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
        return _server_error("Failed to retrieve alerts.", exc)
    finally:
        session.close()


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5004))
    # Audit fix: debug mode is now opt-in via FLASK_ENV, not hardcoded on.
    # Werkzeug's debug mode exposes an interactive code-execution console on
    # unhandled errors - a real risk when the container is reachable
    # externally. Set FLASK_ENV=development locally if you need it.
    debug_enabled = os.getenv("FLASK_ENV", "production").lower() == "development"
    app.run(host="0.0.0.0", port=port, debug=debug_enabled, use_reloader=False)
