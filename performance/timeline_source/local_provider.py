"""
LocalMockTimelineProvider - TEMPORARY development-only implementation of
TimelineProvider, backed by Performance's own `projects`/`phases` Postgres
tables.

This is a stand-in for the real Timeline component, which does not exist
yet. It is intentionally kept thin: it only reads/writes the same tables
Performance already had, just funnels all access through the
TimelineProvider interface instead of scattering raw SQL across main.py
and dashboard_feed.py.

`create_project`/`create_phase` are NOT part of the TimelineProvider
interface (see base.py) on purpose - in the final architecture, Timeline
owns creating projects/phases, not Performance. They exist here only so
the temporary /schedule dev-seeding endpoint has something to call. When
TIMELINE_SOURCE=remote is introduced, /schedule either gets removed or
redirected to call Timeline's own project-creation API instead - it will
NOT call anything on RemoteTimelineProvider, since that class intentionally
does not implement writes.
"""

from datetime import date, datetime

from sqlalchemy import text

from database.db import get_db_session
from pipeline.spi_calculator import calculate_planned_percent
from timeline_source.base import TimelineProvider


def _derive_schedule_status(planned_start, planned_end, as_of: date = None) -> str:
    """
    Where a phase sits relative to its PLANNED DATES only - a pure calendar
    fact, derivable from Timeline-owned data alone.

    Deliberately never returns "complete": passing a planned end date means
    the phase is PAST ITS PLANNED END, not that any work actually happened.
    Whether a phase is genuinely complete/on-track/at-risk depends on
    recorded progress, which is Performance-owned data this provider must
    not reach into (see base.py) - that combined status is derived in
    monitoring/dashboard_feed.py instead.
    """
    as_of = as_of or date.today()
    if planned_start and as_of < planned_start:
        return "not_started"
    if planned_end and as_of > planned_end:
        return "past_planned_end"
    return "in_progress"


def _derive_expected_progress(planned_start, planned_end, as_of: date = None) -> float:
    if not planned_start or not planned_end:
        return 0.0
    try:
        return calculate_planned_percent(planned_start, planned_end, as_of_date=as_of)
    except ValueError:
        return 0.0


def _project_row_to_dict(row) -> dict:
    return {
        "project_id": row[0],
        "name": row[1],
        "district": row[2],
        "province": row[3],
        "floors": row[4],
        "building_type": row[5],
        "latitude": row[6],
        "longitude": row[7],
    }


def _phase_row_to_dict(row) -> dict:
    # row: id, project_id, phase_group, sub_phase, sequence, planned_start, planned_end, planned_duration_days
    planned_start, planned_end = row[5], row[6]
    return {
        "phase_id": row[0],
        "project_id": row[1],
        "phase_group": row[2],
        "sub_phase": row[3],
        "sequence": row[4],
        "planned_start": planned_start.isoformat() if planned_start else None,
        "planned_end": planned_end.isoformat() if planned_end else None,
        "planned_duration_days": row[7],
        "expected_progress_percent": _derive_expected_progress(planned_start, planned_end),
        "schedule_status": _derive_schedule_status(planned_start, planned_end),
    }


class LocalMockTimelineProvider(TimelineProvider):
    def list_projects(self) -> list[dict]:
        session = get_db_session()
        try:
            rows = session.execute(
                text(
                    """
                    SELECT id, name, district, province, floors, building_type,
                           latitude, longitude
                    FROM projects
                    ORDER BY id DESC
                    """
                )
            ).fetchall()
            return [_project_row_to_dict(row) for row in rows]
        finally:
            session.close()

    def get_project(self, project_id: int) -> dict | None:
        session = get_db_session()
        try:
            row = session.execute(
                text(
                    """
                    SELECT id, name, district, province, floors, building_type,
                           latitude, longitude
                    FROM projects
                    WHERE id = :project_id
                    """
                ),
                {"project_id": project_id},
            ).fetchone()
            return _project_row_to_dict(row) if row else None
        finally:
            session.close()

    def list_phases(self, project_id: int) -> list[dict]:
        session = get_db_session()
        try:
            rows = session.execute(
                text(
                    """
                    SELECT id, project_id, phase_group, sub_phase, sequence,
                           planned_start, planned_end, planned_duration_days
                    FROM phases
                    WHERE project_id = :project_id
                    ORDER BY sequence ASC
                    """
                ),
                {"project_id": project_id},
            ).fetchall()
            return [_phase_row_to_dict(row) for row in rows]
        finally:
            session.close()

    def get_phase(self, phase_id: int) -> dict | None:
        session = get_db_session()
        try:
            row = session.execute(
                text(
                    """
                    SELECT p.id, p.project_id, p.phase_group, p.sub_phase, p.sequence,
                           p.planned_start, p.planned_end, p.planned_duration_days,
                           pr.district, pr.province, pr.floors,
                           pr.latitude, pr.longitude
                    FROM phases p
                    JOIN projects pr ON pr.id = p.project_id
                    WHERE p.id = :phase_id
                    """
                ),
                {"phase_id": phase_id},
            ).fetchone()
            if not row:
                return None
            phase = _phase_row_to_dict(row[:8])
            phase["district"] = row[8]
            phase["province"] = row[9]
            phase["floors"] = row[10]
            phase["latitude"] = row[11]
            phase["longitude"] = row[12]
            return phase
        finally:
            session.close()

    # --- Mock-only write helpers, NOT part of the TimelineProvider interface ---
    # Used exclusively by the temporary /schedule dev-seeding endpoint.

    def create_project(
        self,
        session,
        *,
        name: str,
        district: str,
        province: str,
        floors: int,
        building_type: str,
        latitude: float = None,
        longitude: float = None,
    ):
        from database.db import Project

        project_row = Project(
            name=name.strip(),
            district=district.strip(),
            province=province.strip(),
            floors=int(floors),
            building_type=building_type.strip(),
            latitude=float(latitude) if latitude is not None else None,
            longitude=float(longitude) if longitude is not None else None,
        )
        session.add(project_row)
        session.flush()
        return project_row.id

    def update_project_location(self, session, *, project_id: int, latitude: float, longitude: float) -> dict | None:
        """
        Mock-only write helper, NOT part of the TimelineProvider interface -
        same reasoning as create_project/create_phase above. Used exclusively
        by the temporary PATCH /project/<id>/location dev endpoint, so a
        house owner can move the pin after the project already exists rather
        than having the site location be permanently fixed at creation time.
        """
        from database.db import Project

        project_row = session.get(Project, project_id)
        if not project_row:
            return None
        project_row.latitude = float(latitude)
        project_row.longitude = float(longitude)
        session.flush()
        return {"project_id": project_id, "latitude": project_row.latitude, "longitude": project_row.longitude}

    def create_phase(
        self,
        session,
        *,
        project_id: int,
        phase_group: str,
        sub_phase: str,
        planned_start,
        planned_end,
        planned_duration_days: int,
        sequence: int,
    ):
        from database.db import Phase

        phase_row = Phase(
            project_id=project_id,
            phase_group=phase_group,
            sub_phase=sub_phase,
            planned_start=planned_start,
            planned_end=planned_end,
            planned_duration_days=int(planned_duration_days),
            sequence=int(sequence),
        )
        session.add(phase_row)
        session.flush()
        return phase_row.id
