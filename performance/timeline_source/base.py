"""
Timeline Data Interface.

ARCHITECTURE NOTE (do not remove): Performance does NOT own project/phase
schedule data. In the final system, the separate Timeline component is the
source of truth for this data. This interface is the ONLY way any
Performance business logic (SPI, feature engineering, prediction, RAG,
dashboard) is allowed to read project/phase data - nothing else in this
codebase should run SQL against the `projects`/`phases` tables directly.

Today, TIMELINE_SOURCE=local backs this interface with Performance's own
Postgres tables (see local_provider.py) purely as a development/testing
convenience, because the real Timeline component/API does not exist yet.
That is explicitly TEMPORARY. When the real Timeline component is ready,
implement RemoteTimelineProvider's methods against its API (see
remote_provider.py) and flip TIMELINE_SOURCE=remote - no other file in
Performance needs to change, because nothing else talks to this data any
other way.

Field shapes returned by every implementation must match exactly, since
callers (main.py, dashboard_feed.py) depend on these dict shapes:

Project dict:
    {
        "project_id": int,
        "name": str,
        "district": str,
        "province": str,
        "floors": int,
        "building_type": str,
        "latitude": float or None,   # exact site location, optional
        "longitude": float or None,  # exact site location, optional
    }

Phase dict (as returned by list_phases):
    {
        "phase_id": int,
        "project_id": int,
        "phase_group": str,
        "sub_phase": str,
        "sequence": int,
        "planned_start": "YYYY-MM-DD" or None,
        "planned_end": "YYYY-MM-DD" or None,
        "planned_duration_days": int or None,
        "expected_progress_percent": float,   # derived, not stored
        # Derived calendar fact only: "not_started" | "in_progress" |
        # "past_planned_end". Note this is NOT a completion status - a phase
        # past its planned end date has not necessarily had any work done.
        # The homeowner-facing status (Not Started / On Track / At Risk /
        # Overdue / Completed) additionally needs recorded progress, which is
        # Performance-owned, so it is derived in monitoring/dashboard_feed.py
        # rather than here.
        "schedule_status": str,
    }

Phase-with-project-context dict (as returned by get_phase - used by the
SPI/prediction endpoints, which need the parent project's location/floors
joined in):
    {
        **Phase dict fields above,
        "district": str,
        "province": str,
        "floors": int,
        "latitude": float or None,
        "longitude": float or None,
    }
"""

from abc import ABC, abstractmethod


class TimelineProvider(ABC):
    @abstractmethod
    def list_projects(self) -> list[dict]:
        """Return all projects. Feeds the Form 1 project dropdown."""
        raise NotImplementedError

    @abstractmethod
    def get_project(self, project_id: int) -> dict | None:
        """Return one project, or None if not found."""
        raise NotImplementedError

    @abstractmethod
    def list_phases(self, project_id: int) -> list[dict]:
        """Return all phases for a project, ordered by sequence."""
        raise NotImplementedError

    @abstractmethod
    def get_phase(self, phase_id: int) -> dict | None:
        """
        Return one phase joined with its parent project's district/
        province/floors, or None if not found. Used by /progress/spi and
        /progress/predict, which need this combined context.
        """
        raise NotImplementedError
