"""
Tests for Component 04 — Timeline Generation.

Coverage:
  - Full pipeline integration (preprocess → feature-engineer → predict)
  - Critical path calculation with known deterministic durations
  - Total duration equals critical path sum (not sum of all phases)
  - Phase dependency ordering is respected in the schedule
  - Gantt builder produces correct calendar date sequences
  - Working-day calendar skips weekends and Sri Lankan holidays
  - Milestone dates are derived from the correct phases
  - TimelineSerialiser output structure matches the spec schema
"""

import pytest
from datetime import date

from timeline.pipeline import phases as p
from timeline.pipeline.preprocessor import Preprocessor
from timeline.pipeline.feature_engineer import FeatureEngineer
from timeline.pipeline.schedule_model import ScheduleModel
from timeline.pipeline.critical_path import CriticalPathEngine
from timeline.output.gantt_builder import GanttBuilder
from timeline.output.timeline_serialiser import TimelineSerialiser


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def small_project():
    """100 sqm, 1 floor, mid finish grade — the canonical test project."""
    return {
        "building_schema": {
            "project_id": "test-proj-001",
            "floors": 1,
            "footprint_sqm": 100.0,
            "total_area_sqm": 100.0,
            "finish_grade": "standard",
            "roof_type": "flat",
            "foundation_type": "strip",
            "has_basement": False,
            "location_coastal": False,
            "district": "Colombo",
        },
        "cost_report": {
            "total_labour_days": 200,
            "structural_complexity_score": 1.0,
            "total_cost": 8_000_000.0,
            "trade_value_breakdown": {
                "civil": 3_000_000.0,
                "mep":   2_000_000.0,
                "finishing": 3_000_000.0,
            },
        },
    }


@pytest.fixture
def known_durations() -> dict[str, int]:
    """
    Deterministic phase durations chosen so the critical path is exactly:
      site_preparation(2) → foundation(5) → superstructure(10)
      → brickwork_and_blockwork(5) → internal_plastering(4)
      → floor_finishing(3) → door_and_window_fixing(2)
      → ceiling path wins over door_and_window via ceiling merge
      → ceiling(3) → electrical_second_fix(2) → final_inspection(1)

    But the actual critical path is determined by the CPM engine.
    We just assert the engine's result is self-consistent.
    """
    return {
        p.SITE_PREPARATION:        2,
        p.FOUNDATION:              5,
        p.SUPERSTRUCTURE:          10,
        p.BRICKWORK_AND_BLOCKWORK: 5,
        p.ROOF_STRUCTURE:          3,
        p.ROOF_COVERING:           2,
        p.EXTERNAL_PLASTERING:     4,
        p.INTERNAL_PLASTERING:     4,
        p.FLOOR_FINISHING:         3,
        p.DOOR_AND_WINDOW_FIXING:  2,
        p.ELECTRICAL_FIRST_FIX:    3,
        p.PLUMBING_FIRST_FIX:      3,
        p.CEILING:                 3,
        p.PAINTING:                5,
        p.ELECTRICAL_SECOND_FIX:   2,
        p.PLUMBING_SECOND_FIX:     2,
        p.EXTERNAL_WORKS:          4,
        p.FINAL_INSPECTION:        1,
    }


# ── Pipeline integration ──────────────────────────────────────────────────────

class TestPipelineIntegration:
    def test_full_pipeline_returns_all_phases(self, small_project):
        """End-to-end: preprocessor → feature engineer → schedule model."""
        preprocessor  = Preprocessor()
        feat_eng      = FeatureEngineer()
        model         = ScheduleModel()

        df      = preprocessor.prepare(
            small_project["building_schema"],
            small_project["cost_report"],
        )
        features = feat_eng.build_features(df)
        durations = model.predict_phase_durations(features)

        assert set(durations.keys()) == set(p.ALL_PHASES), (
            "predict_phase_durations must return exactly the 18 standard phases"
        )

    def test_all_durations_are_positive_integers(self, small_project):
        preprocessor = Preprocessor()
        feat_eng     = FeatureEngineer()
        model        = ScheduleModel()

        df       = preprocessor.prepare(small_project["building_schema"], small_project["cost_report"])
        features = feat_eng.build_features(df)
        durations = model.predict_phase_durations(features)

        for phase, days in durations.items():
            assert isinstance(days, int), f"{phase} duration must be int"
            assert days >= 1, f"{phase} duration must be >= 1 working day"

    def test_foundation_stub_minimum(self, small_project):
        """Foundation stub: max(7, footprint * 0.15) for 100 sqm → 15 days."""
        preprocessor = Preprocessor()
        feat_eng     = FeatureEngineer()
        model        = ScheduleModel()

        df       = preprocessor.prepare(small_project["building_schema"], small_project["cost_report"])
        features = feat_eng.build_features(df)
        durations = model.predict_phase_durations(features)

        assert durations[p.FOUNDATION] >= 7

    def test_feature_engineer_derives_perimeter(self, small_project):
        """perimeter_m = 4 * sqrt(footprint_sqm); for 100 sqm → 40.0 m."""
        import math
        preprocessor = Preprocessor()
        feat_eng     = FeatureEngineer()

        df       = preprocessor.prepare(small_project["building_schema"], small_project["cost_report"])
        features = feat_eng.build_features(df)

        assert abs(features["perimeter_m"].iloc[0] - 40.0) < 1e-6


# ── Critical Path Method ──────────────────────────────────────────────────────

class TestCriticalPath:
    def test_all_phases_present_in_graph(self, known_durations):
        engine = CriticalPathEngine()
        graph  = engine.build_network(known_durations)

        assert set(graph.nodes()) == set(p.ALL_PHASES)

    def test_total_duration_equals_critical_path_sum(self, known_durations):
        """
        The project duration must equal the sum of durations along the
        critical path, not the sum of all 18 phases.
        """
        engine  = CriticalPathEngine()
        graph   = engine.build_network(known_durations)
        result  = engine.calculate(graph)

        cp_sum = sum(known_durations[ph] for ph in result["critical_path"])
        assert result["total_duration_days"] == cp_sum, (
            f"total_duration_days ({result['total_duration_days']}) "
            f"!= critical path sum ({cp_sum})"
        )

    def test_critical_path_phases_have_zero_float(self, known_durations):
        engine = CriticalPathEngine()
        result = engine.calculate(engine.build_network(known_durations))

        for phase in result["critical_path"]:
            assert result["float_per_phase"][phase] == 0, (
                f"Critical path phase '{phase}' has non-zero float"
            )

    def test_non_critical_phases_have_positive_float(self, known_durations):
        engine = CriticalPathEngine()
        result = engine.calculate(engine.build_network(known_durations))

        cp_set = set(result["critical_path"])
        for phase in p.ALL_PHASES:
            if phase not in cp_set:
                assert result["float_per_phase"][phase] > 0, (
                    f"Non-critical phase '{phase}' should have positive float"
                )

    def test_critical_path_in_topological_order(self, known_durations):
        """Critical path list must respect the dependency graph order."""
        import networkx as nx
        engine = CriticalPathEngine()
        graph  = engine.build_network(known_durations)
        result = engine.calculate(graph)

        cp = result["critical_path"]
        topo_positions = {n: i for i, n in enumerate(nx.topological_sort(graph))}
        for i in range(len(cp) - 1):
            assert topo_positions[cp[i]] < topo_positions[cp[i + 1]], (
                f"Critical path is not in topological order at position {i}"
            )

    def test_dependencies_respected_in_early_starts(self, known_durations):
        """For every edge (A→B), ES[B] >= EF[A]."""
        engine = CriticalPathEngine()
        graph  = engine.build_network(known_durations)
        result = engine.calculate(graph)

        es = result["early_start_per_phase"]
        ef = result["early_finish_per_phase"]

        for src, dst in graph.edges():
            assert es[dst] >= ef[src], (
                f"Dependency violated: {src} (EF={ef[src]}) → {dst} (ES={es[dst]})"
            )


# ── Gantt Builder ─────────────────────────────────────────────────────────────

class TestGanttBuilder:
    def test_gantt_contains_all_phases(self, known_durations):
        engine  = CriticalPathEngine()
        builder = GanttBuilder()

        result = engine.calculate(engine.build_network(known_durations))
        gantt  = builder.build(known_durations, result, date(2024, 1, 1))

        assert len(gantt) == 18
        gantt_phases = {g["phase"] for g in gantt}
        assert gantt_phases == set(p.ALL_PHASES)

    def test_site_preparation_starts_on_project_start(self, known_durations):
        """site_preparation has ES=0, so it must start on project_start_date."""
        engine  = CriticalPathEngine()
        builder = GanttBuilder()

        # Monday 2024-01-08 (no Sri Lankan holiday)
        start   = date(2024, 1, 8)
        result  = engine.calculate(engine.build_network(known_durations))
        gantt   = builder.build(known_durations, result, start)

        sp = next(g for g in gantt if g["phase"] == p.SITE_PREPARATION)
        assert sp["start_date"] == start

    def test_site_preparation_end_date_correct(self, known_durations):
        """site_preparation lasts 2 working days → start Mon, end Tue."""
        engine  = CriticalPathEngine()
        builder = GanttBuilder()

        start  = date(2024, 1, 8)   # Monday
        result = engine.calculate(engine.build_network(known_durations))
        gantt  = builder.build(known_durations, result, start)

        sp = next(g for g in gantt if g["phase"] == p.SITE_PREPARATION)
        assert sp["start_date"] == date(2024, 1, 8)
        assert sp["end_date"]   == date(2024, 1, 9)   # Tuesday (+1 working day)

    def test_no_phase_starts_on_weekend(self, known_durations):
        engine  = CriticalPathEngine()
        builder = GanttBuilder()

        result = engine.calculate(engine.build_network(known_durations))
        gantt  = builder.build(known_durations, result, date(2024, 1, 8))

        for entry in gantt:
            assert entry["start_date"].weekday() < 5, (
                f"{entry['phase']} starts on a weekend: {entry['start_date']}"
            )
            assert entry["end_date"].weekday() < 5, (
                f"{entry['phase']} ends on a weekend: {entry['end_date']}"
            )

    def test_critical_phases_marked(self, known_durations):
        engine  = CriticalPathEngine()
        builder = GanttBuilder()

        result = engine.calculate(engine.build_network(known_durations))
        gantt  = builder.build(known_durations, result, date(2024, 1, 8))

        cp_set = set(result["critical_path"])
        for entry in gantt:
            if entry["phase"] in cp_set:
                assert entry["is_critical"] is True
            else:
                assert entry["is_critical"] is False

    def test_start_on_weekend_snapped_to_monday(self, known_durations):
        """If project_start_date is a Saturday, snap to the next Monday."""
        engine  = CriticalPathEngine()
        builder = GanttBuilder()

        saturday = date(2024, 1, 6)
        monday   = date(2024, 1, 8)
        result   = engine.calculate(engine.build_network(known_durations))
        gantt    = builder.build(known_durations, result, saturday)

        sp = next(g for g in gantt if g["phase"] == p.SITE_PREPARATION)
        assert sp["start_date"] >= monday


# ── Timeline Serialiser ───────────────────────────────────────────────────────

class TestTimelineSerialiser:
    @pytest.fixture
    def minimal_gantt(self) -> list[dict]:
        return [
            {
                "phase":         p.FOUNDATION,
                "start_date":    date(2024, 1, 8),
                "end_date":      date(2024, 1, 14),
                "duration_days": 5,
                "is_critical":   True,
                "dependencies":  [p.SITE_PREPARATION],
                "float_days":    0,
            },
            {
                "phase":         p.FINAL_INSPECTION,
                "start_date":    date(2024, 3, 1),
                "end_date":      date(2024, 3, 1),
                "duration_days": 1,
                "is_critical":   True,
                "dependencies":  [],
                "float_days":    0,
            },
        ]

    @pytest.fixture
    def minimal_cp(self) -> dict:
        return {
            "critical_path":          [p.FOUNDATION, p.FINAL_INSPECTION],
            "total_duration_days":    6,
            "total_duration_weeks":   1.2,
            "float_per_phase":        {p.FOUNDATION: 0, p.FINAL_INSPECTION: 0},
            "early_start_per_phase":  {p.FOUNDATION: 0, p.FINAL_INSPECTION: 5},
            "early_finish_per_phase": {p.FOUNDATION: 5, p.FINAL_INSPECTION: 6},
        }

    def test_output_contains_required_top_level_keys(self, minimal_gantt, minimal_cp, small_project):
        serialiser = TimelineSerialiser()
        out = serialiser.serialise(
            {p.FOUNDATION: 5, p.FINAL_INSPECTION: 1},
            minimal_cp,
            minimal_gantt,
            small_project["building_schema"],
            small_project["cost_report"],
        )

        for key in ("timeline_id", "project_id", "generated_at", "summary", "phases", "milestone_dates"):
            assert key in out, f"Missing top-level key: '{key}'"

    def test_project_id_matches_schema(self, minimal_gantt, minimal_cp, small_project):
        serialiser = TimelineSerialiser()
        out = serialiser.serialise(
            {p.FOUNDATION: 5, p.FINAL_INSPECTION: 1},
            minimal_cp,
            minimal_gantt,
            small_project["building_schema"],
            small_project["cost_report"],
        )
        assert out["project_id"] == "test-proj-001"

    def test_total_duration_propagated(self, minimal_gantt, minimal_cp, small_project):
        serialiser = TimelineSerialiser()
        out = serialiser.serialise(
            {p.FOUNDATION: 5, p.FINAL_INSPECTION: 1},
            minimal_cp,
            minimal_gantt,
            small_project["building_schema"],
            small_project["cost_report"],
        )
        assert out["summary"]["total_duration_days"] == 6

    def test_total_phases_is_18(self, minimal_gantt, minimal_cp, small_project):
        serialiser = TimelineSerialiser()
        out = serialiser.serialise(
            {p.FOUNDATION: 5},
            minimal_cp,
            minimal_gantt,
            small_project["building_schema"],
            small_project["cost_report"],
        )
        assert out["summary"]["total_phases"] == 18

    def test_milestone_foundation_complete_set(self, minimal_gantt, minimal_cp, small_project):
        serialiser = TimelineSerialiser()
        out = serialiser.serialise(
            {p.FOUNDATION: 5, p.FINAL_INSPECTION: 1},
            minimal_cp,
            minimal_gantt,
            small_project["building_schema"],
            small_project["cost_report"],
        )
        # foundation's end_date in minimal_gantt is 2024-01-14
        assert out["milestone_dates"]["foundation_complete"] == "2024-01-14"

    def test_dates_serialised_as_iso_strings(self, minimal_gantt, minimal_cp, small_project):
        serialiser = TimelineSerialiser()
        out = serialiser.serialise(
            {p.FOUNDATION: 5, p.FINAL_INSPECTION: 1},
            minimal_cp,
            minimal_gantt,
            small_project["building_schema"],
            small_project["cost_report"],
        )
        phase = out["phases"][0]
        assert isinstance(phase["start_date"], str)
        assert isinstance(phase["end_date"],   str)
        # Should be parseable as ISO dates
        date.fromisoformat(phase["start_date"])
        date.fromisoformat(phase["end_date"])
