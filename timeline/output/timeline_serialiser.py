"""
TimelineSerialiser — Component 04 Output Step 2.

Assembles the final Timeline JSON document from the outputs of the pipeline
and the Gantt builder.  This document is what gets stored in PostgreSQL and
returned to the API caller.
"""

import uuid
from datetime import date, datetime
from typing import Any

from timeline.pipeline.phases import ALL_PHASES, MILESTONE_PHASES


class TimelineSerialiser:
    """
    Converts pipeline outputs into the canonical Timeline JSON structure.

    The output schema is intentionally flat and self-contained so that
    downstream components (Component 05 — Performance Monitoring) and the
    gateway can consume it without referencing any internal objects.
    """

    def serialise(
        self,
        phase_durations: dict[str, int],
        critical_path: dict[str, Any],
        gantt: list[dict],
        building_schema: dict,
        cost_report: dict,
    ) -> dict:
        """
        Build the complete Timeline JSON document.

        Args:
            phase_durations: {phase_name: working_days} from ScheduleModel.
            critical_path:   Output of CriticalPathEngine.calculate().
            gantt:           Output of GanttBuilder.build() — list of phase dicts.
            building_schema: Original Component 01 payload (for project_id).
            cost_report:     Original Component 02 payload (metadata only).

        Returns:
            dict matching the Timeline JSON schema::

                {
                    "timeline_id": str,
                    "project_id":  str,
                    "generated_at": ISO datetime str,
                    "summary": { ... },
                    "phases": [ ...gantt entries with ISO date strings... ],
                    "milestone_dates": { ... },
                }
        """
        timeline_id = str(uuid.uuid4())
        project_id  = building_schema.get("project_id", "UNKNOWN")
        generated_at = datetime.utcnow().isoformat() + "Z"

        # ── Project start / end from Gantt data ───────────────────────────────
        if gantt:
            project_start       = min(g["start_date"] for g in gantt)
            project_completion  = max(g["end_date"]   for g in gantt)
        else:
            project_start = project_completion = date.today()

        # ── Gantt phases — serialise dates to ISO strings ─────────────────────
        serialised_phases = [
            {
                "phase":         g["phase"],
                "start_date":    self._to_iso(g["start_date"]),
                "end_date":      self._to_iso(g["end_date"]),
                "duration_days": g["duration_days"],
                "is_critical":   g["is_critical"],
                "dependencies":  g["dependencies"],
                "float_days":    g["float_days"],
            }
            for g in gantt
        ]

        # ── Milestone dates ───────────────────────────────────────────────────
        # Build a lookup {phase_name: end_date_ISO} from the gantt list once
        gantt_end: dict[str, str] = {g["phase"]: self._to_iso(g["end_date"]) for g in gantt}

        milestone_dates = {
            label: gantt_end.get(phase)
            for label, phase in MILESTONE_PHASES.items()
        }

        return {
            "timeline_id":  timeline_id,
            "project_id":   project_id,
            "generated_at": generated_at,
            "summary": {
                "total_duration_days":        critical_path.get("total_duration_days"),
                "total_duration_weeks":       critical_path.get("total_duration_weeks"),
                "projected_start_date":       self._to_iso(project_start),
                "projected_completion_date":  self._to_iso(project_completion),
                "critical_path_phases":       critical_path.get("critical_path", []),
                "total_phases":               len(ALL_PHASES),
            },
            "phases":          serialised_phases,
            "milestone_dates": milestone_dates,
        }

    # ── Private helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _to_iso(value: Any) -> str | None:
        """Return ISO 8601 string for a date/datetime, or None."""
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        return None
