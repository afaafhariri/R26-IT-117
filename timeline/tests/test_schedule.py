import pytest
from datetime import date
from timeline.pipeline import phases
from timeline.pipeline.preprocessor import Preprocessor
from timeline.pipeline.feature_engineer import FeatureEngineer
from timeline.pipeline.schedule_model import ScheduleModel
from timeline.pipeline.critical_path import CriticalPathEngine
from timeline.output.gantt_builder import GanttBuilder
from timeline.output.timeline_serialiser import TimelineSerialiser

@pytest.fixture
def sample_project():
    return {
        "building_schema": {
            "project_id": "test-123",
            "floors": 1,
            "footprint_sqm": 100.0,
            "total_area_sqm": 100.0,
            "finish_grade": "standard",
            "roof_type": "flat",
            "foundation_type": "strip",
            "location_coastal": False
        },
        "cost_report": {
            "total_labour_days": 200,
            "structural_complexity_score": 1.0,
            "trade_value_breakdown": {}
        }
    }

def test_pipeline_integration(sample_project):
    preprocessor = Preprocessor()
    feature_engineer = FeatureEngineer()
    schedule_model = ScheduleModel()
    
    df = preprocessor.prepare(sample_project["building_schema"], sample_project["cost_report"])
    features = feature_engineer.build_features(df)
    durations = schedule_model.predict_phase_durations(features)
    
    assert phases.FOUNDATION in durations
    assert durations[phases.FOUNDATION] >= 7

def test_critical_path_and_dates():
    # Use known durations for a deterministic test
    known_durations = {
        phases.SITE_PREPARATION: 2,
        phases.FOUNDATION: 5,
        phases.SUPERSTRUCTURE: 10,
        phases.BRICKWORK_AND_BLOCKWORK: 5,
        phases.ROOF_STRUCTURE: 3,
        phases.ROOF_COVERING: 2,
        phases.EXTERNAL_PLASTERING: 4,
        phases.INTERNAL_PLASTERING: 4,
        phases.FLOOR_FINISHING: 3,
        phases.DOOR_AND_WINDOW_FIXING: 2,
        phases.ELECTRICAL_FIRST_FIX: 3,
        phases.PLUMBING_FIRST_FIX: 3,
        phases.CEILING: 3,
        phases.PAINTING: 5,
        phases.ELECTRICAL_SECOND_FIX: 2,
        phases.PLUMBING_SECOND_FIX: 2,
        phases.EXTERNAL_WORKS: 4,
        phases.FINAL_INSPECTION: 1,
    }
    
    cp_engine = CriticalPathEngine()
    gantt_builder = GanttBuilder()
    
    graph = cp_engine.build_network(known_durations)
    cp_result = cp_engine.calculate(graph)
    
    # E.g. SitePrep(2) -> Found(5) -> SuperStruct(10) -> Brick(5) -> IntPlaster(4) -> Floor(3) -> DoorWin(2) -> Final(1)
    # 2 + 5 + 10 + 5 + 4 + 3 + 2 + 1 = 32 working days? Let's check max path
    assert "critical_path" in cp_result
    assert cp_result["total_duration_days"] > 0
    
    # Test total duration matches length of critical path (sum of dependencies)
    cp_sum = sum(known_durations[p] for p in cp_result["critical_path"])
    assert cp_result["total_duration_days"] == cp_sum

    # Gantt Calendar dates test
    # Start on a Monday
    start_date = date(2023, 1, 2)  
    gantt = gantt_builder.build(known_durations, cp_result, start_date)
    
    assert len(gantt) == 18
    # Site preparation should start on Jan 2 and end on Jan 3 (2 days)
    # Foundation starts on Jan 4
    for item in gantt:
        if item["phase"] == phases.SITE_PREPARATION:
            assert item["start_date"] == date(2023, 1, 2)
            assert item["end_date"] == date(2023, 1, 3)

def test_timeline_serialisation(sample_project):
    """
    Test milestone dates and final output structure
    """
    timeline_engine = TimelineSerialiser()
    gantt = [
        {
            "phase": phases.FOUNDATION,
            "start_date": date(2023, 1, 1),
            "end_date": date(2023, 1, 5),
            "duration_days": 5, "is_critical": True, "dependencies": [], "float_days": 0
        }
    ]
    
    cp_result = {
        "critical_path": [phases.FOUNDATION],
        "total_duration_days": 5,
        "total_duration_weeks": 1.0,
        "float_per_phase": {phases.FOUNDATION: 0},
        "early_start_per_phase": {phases.FOUNDATION: 0},
        "early_finish_per_phase": {phases.FOUNDATION: 5}
    }
    
    out = timeline_engine.serialise(
        {phases.FOUNDATION: 5},
        cp_result,
        gantt,
        sample_project["building_schema"],
        sample_project["cost_report"]
    )
    
    assert out["project_id"] == "test-123"
    assert out["summary"]["total_duration_days"] == 5
    assert out["milestone_dates"]["foundation_complete"] is not None
