"""
pipeline/critical_path.py — Component 03 Pipeline Step 4.

Implements the Critical Path Method (CPM) over the 5-phase sequential
dependency graph and converts working-day offsets to real Sri Lankan
calendar dates.

CPM definitions
───────────────
  ES  — Early Start  : earliest working day the phase can begin (0-indexed)
  EF  — Early Finish : ES + duration_days
  LF  — Late Finish  : latest day a phase can end without delaying the project
  LS  — Late Start   : LF − duration_days
  TF  — Total Float  : LS − ES  (0 = on the critical path)
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any

import holidays
import networkx as nx

from pipeline.phases import ALL_PHASES, PHASE_DEPENDENCIES

# ── Constants ─────────────────────────────────────────────────────────────────

_WORK_DAYS_PER_WEEK: float = 5.0
_LK_HOLIDAYS = set()


# ── Calendar helpers ──────────────────────────────────────────────────────────

def _is_working_day(d: date) -> bool:
    return d.weekday() < 5 and d not in _LK_HOLIDAYS


def _next_working_day(d: date) -> date:
    """Return d if it is a working day, otherwise advance to the next one."""
    while not _is_working_day(d):
        d += timedelta(days=1)
    return d


def _add_working_days(start: date, n: int) -> date:
    """
    Advance start by exactly n working days.
    n == 0 returns start itself.
    """
    if n <= 0:
        return start
    current = start
    added = 0
    while added < n:
        current += timedelta(days=1)
        if _is_working_day(current):
            added += 1
    return current


def _weeks_to_days(weeks: float) -> int:
    """Convert decimal weeks to whole working days (always round up)."""
    return max(1, math.ceil(weeks * _WORK_DAYS_PER_WEEK))


# ── Engine ────────────────────────────────────────────────────────────────────

class CriticalPathEngine:
    """
    Builds the 5-phase DAG, runs CPM, and produces calendar-dated Gantt tasks.
    """

    # ── Public: schedule calculation ─────────────────────────────────────────

    def calculate(
        self,
        phase_weeks: dict[str, float],
        project_start_date: date,
    ) -> dict[str, Any]:
        """
        Run the full CPM pipeline for the given phase durations.

        Args:
            phase_weeks:          {phase_name: predicted_weeks} from ScheduleModel.
            project_start_date:   Desired project start date (date object).
                                  Snapped forward to the next working day if it
                                  falls on a weekend or Sri Lankan public holiday.

        Returns:
            dict with keys:
              gantt_tasks          list[dict]  — one entry per phase (see below)
              critical_path        list[str]   — phases with TF == 0, topo order
              float_per_phase      dict[str, int]  — total float in working days
              total_duration_days  int
              total_duration_weeks float
              project_start_date   str  (ISO 8601)
              project_end_date     str  (ISO 8601)

            Each gantt_tasks entry::

              {
                "id":             str,   # phase name — used as Gantt row key
                "text":           str,   # display label
                "start_date":     str,   # ISO date
                "end_date":       str,   # ISO date (last working day of phase)
                "duration":       int,   # working days
                "duration_weeks": float,
                "is_critical":    bool,
                "float_days":     int,
                "dependencies":   list[str],
                "progress":       float, # 0.0 — placeholder for front-end
              }

        Raises:
            ValueError: If a phase is missing from phase_weeks or the
                        dependency graph contains a cycle.
        """
        # ── Validate ──────────────────────────────────────────────────────────
        missing = [p for p in ALL_PHASES if p not in phase_weeks]
        if missing:
            raise ValueError(
                f"CriticalPathEngine.calculate: missing phases: {missing}"
            )

        # ── Convert weeks → working days ──────────────────────────────────────
        durations: dict[str, int] = {
            phase: _weeks_to_days(phase_weeks[phase])
            for phase in ALL_PHASES
        }

        # ── Build DAG ─────────────────────────────────────────────────────────
        G = nx.DiGraph()
        for phase in ALL_PHASES:
            G.add_node(phase, duration=durations[phase])
        for phase, preds in PHASE_DEPENDENCIES.items():
            for pred in preds:
                G.add_edge(pred, phase)

        if not nx.is_directed_acyclic_graph(G):
            raise ValueError(
                "Phase dependency graph contains a cycle — "
                "check PHASE_DEPENDENCIES in phases.py."
            )

        topo: list[str] = list(nx.topological_sort(G))

        # ── Forward pass — ES / EF ────────────────────────────────────────────
        es: dict[str, int] = {}
        ef: dict[str, int] = {}
        for node in topo:
            predecessors = list(G.predecessors(node))
            es[node] = max((ef[p] for p in predecessors), default=0)
            ef[node] = es[node] + G.nodes[node]["duration"]

        total_days: int = max(ef.values())

        # ── Backward pass — LF / LS ───────────────────────────────────────────
        lf: dict[str, int] = {}
        ls: dict[str, int] = {}
        for node in reversed(topo):
            successors = list(G.successors(node))
            lf[node] = min((ls[s] for s in successors), default=total_days)
            ls[node] = lf[node] - G.nodes[node]["duration"]

        # ── Float and critical path ───────────────────────────────────────────
        total_float: dict[str, int] = {n: ls[n] - es[n] for n in G.nodes()}
        critical_path: list[str]    = [n for n in topo if total_float[n] == 0]

        # ── Map to calendar dates ─────────────────────────────────────────────
        effective_start = _next_working_day(project_start_date)

        gantt_tasks: list[dict] = []
        for phase in ALL_PHASES:
            dur         = durations[phase]
            phase_start = _add_working_days(effective_start, es[phase])
            # End date = last working day of the phase (inclusive)
            phase_end   = _add_working_days(phase_start, dur - 1) if dur > 1 else phase_start

            gantt_tasks.append({
                "id":             phase,
                "text":           phase,
                "start_date":     phase_start.isoformat(),
                "end_date":       phase_end.isoformat(),
                "duration":       dur,
                "duration_weeks": round(phase_weeks[phase], 1),
                "is_critical":    phase in critical_path,
                "float_days":     total_float[phase],
                "dependencies":   PHASE_DEPENDENCIES.get(phase, []),
                "progress":       0.0,
            })

        project_end = _add_working_days(effective_start, total_days - 1)

        return {
            "gantt_tasks":          gantt_tasks,
            "critical_path":        critical_path,
            "float_per_phase":      total_float,
            "total_duration_days":  total_days,
            "total_duration_weeks": round(total_days / _WORK_DAYS_PER_WEEK, 1),
            "project_start_date":   effective_start.isoformat(),
            "project_end_date":     project_end.isoformat(),
        }

    # ── Public: deviation analysis (POST /progress) ───────────────────────────

    @staticmethod
    def compute_deviation(
        planned_weeks: dict[str, float],
        actual_weeks: dict[str, float],
    ) -> dict[str, Any]:
        """
        Compare planned vs actual phase durations.

        Only phases present in BOTH dicts are evaluated — partial site
        reporting (e.g. only Foundation and Structural complete so far)
        is handled gracefully.

        Args:
            planned_weeks: Original model predictions  {phase: weeks}.
            actual_weeks:  Site-reported actual values {phase: weeks}.

        Returns:
            dict with keys:
              phase_deviations       dict[str, dict]  — per-phase breakdown
              overall_deviation_pct  float — weighted mean absolute % deviation
                                     (weight = planned duration, so longer
                                     phases carry more influence)
              alert_level            str — "normal"   if overall < 10 %
                                          "warning"   if 10 % ≤ overall < 25 %
                                          "critical"  if overall ≥ 25 %
        """
        phase_deviations: dict[str, dict] = {}
        weighted_abs_sum: float = 0.0
        weight_total:     float = 0.0

        for phase in ALL_PHASES:
            planned = planned_weeks.get(phase)
            actual  = actual_weeks.get(phase)
            if planned is None or actual is None:
                continue

            planned  = max(float(planned), 0.01)   # guard division by zero
            actual   = float(actual)
            delta    = actual - planned
            delta_pct = (delta / planned) * 100.0

            phase_deviations[phase] = {
                "planned_weeks": round(planned,   1),
                "actual_weeks":  round(actual,    1),
                "delta_weeks":   round(delta,     1),
                "deviation_pct": round(delta_pct, 1),
            }

            weighted_abs_sum += abs(delta_pct) * planned
            weight_total     += planned

        overall_pct = (weighted_abs_sum / weight_total) if weight_total > 0 else 0.0

        if overall_pct < 10.0:
            alert_level = "normal"
        elif overall_pct < 25.0:
            alert_level = "warning"
        else:
            alert_level = "critical"

        return {
            "phase_deviations":      phase_deviations,
            "overall_deviation_pct": round(overall_pct, 2),
            "alert_level":           alert_level,
        }
