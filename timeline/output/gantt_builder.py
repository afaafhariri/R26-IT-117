"""
GanttBuilder — Component 04 Output Step 1.

Translates working-day early-start/finish values from the CPM result into
real calendar dates, accounting for weekends and Sri Lankan public holidays.
"""

from datetime import date, timedelta
from typing import Any

import holidays

from timeline.pipeline.phases import ALL_PHASES, PHASE_DEPENDENCIES


class GanttBuilder:
    """
    Produces a list of Gantt phase objects suitable for direct serialisation
    or rendering by a front-end Gantt library.

    Calendar logic:
    - Working days are Monday–Friday only.
    - Sri Lankan public holidays are excluded using the ``holidays`` library.
    - ``early_start_days == 0`` means the phase starts on ``project_start_date``
      itself (day 0 = first working day).
    """

    def __init__(self) -> None:
        self._lk_holidays = holidays.country_holidays("LK")

    # ── Public API ────────────────────────────────────────────────────────────

    def build(
        self,
        phase_durations: dict[str, int],
        critical_path_result: dict[str, Any],
        project_start_date: date,
    ) -> list[dict]:
        """
        Build the full Gantt chart data structure.

        Args:
            phase_durations:      {phase: working_days}
            critical_path_result: Output of CriticalPathEngine.calculate().
            project_start_date:   Calendar date when the project begins
                                  (must itself be a working day; if not, the
                                  first working day on or after this date is used).

        Returns:
            list[dict] — one entry per phase, in ALL_PHASES order::

                {
                    "phase":         str,
                    "start_date":    date,
                    "end_date":      date,
                    "duration_days": int,
                    "is_critical":   bool,
                    "dependencies":  list[str],
                    "float_days":    int,
                }
        """
        # Snap project_start_date to the next working day if needed
        effective_start = self._next_working_day(project_start_date)

        early_starts   = critical_path_result["early_start_per_phase"]
        float_per_phase= critical_path_result["float_per_phase"]
        critical_nodes = set(critical_path_result["critical_path"])

        gantt: list[dict] = []

        for phase in ALL_PHASES:
            duration     = phase_durations.get(phase, 1)
            early_start  = early_starts.get(phase, 0)
            float_days   = int(float_per_phase.get(phase, 0))
            is_critical  = phase in critical_nodes
            dependencies = PHASE_DEPENDENCIES.get(phase, [])

            # early_start == 0 → phase starts on effective_start itself
            phase_start = self._add_working_days(effective_start, early_start)

            # A phase of duration N occupies working days [start, start+N-1]
            phase_end = self._add_working_days(phase_start, duration - 1) if duration > 1 else phase_start

            gantt.append({
                "phase":         phase,
                "start_date":    phase_start,
                "end_date":      phase_end,
                "duration_days": duration,
                "is_critical":   is_critical,
                "dependencies":  dependencies,
                "float_days":    float_days,
            })

        return gantt

    # ── Private helpers ───────────────────────────────────────────────────────

    def _is_working_day(self, d: date) -> bool:
        """Return True if d is a weekday and not a Sri Lankan public holiday."""
        return d.weekday() < 5 and d not in self._lk_holidays

    def _next_working_day(self, d: date) -> date:
        """Return d if it is a working day, otherwise the next working day."""
        while not self._is_working_day(d):
            d += timedelta(days=1)
        return d

    def _add_working_days(self, start: date, working_days: int) -> date:
        """
        Return the date reached after advancing ``working_days`` working days
        from ``start`` (inclusive — 0 working days returns ``start`` itself).

        Example:
            Monday + 0 → Monday
            Monday + 1 → Tuesday
            Friday + 1 → Monday (next week)
        """
        if working_days <= 0:
            return start

        current = start
        added   = 0
        while added < working_days:
            current += timedelta(days=1)
            if self._is_working_day(current):
                added += 1
        return current
