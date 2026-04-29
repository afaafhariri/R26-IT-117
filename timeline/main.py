from fastapi import FastAPI, HTTPException, Body
from pydantic import BaseModel
from typing import Dict, Any, Optional
from datetime import date
import os

from timeline.pipeline.preprocessor import Preprocessor
from timeline.pipeline.feature_engineer import FeatureEngineer
from timeline.pipeline.schedule_model import ScheduleModel
from timeline.pipeline.critical_path import CriticalPathEngine
from timeline.output.gantt_builder import GanttBuilder
from timeline.output.timeline_serialiser import TimelineSerialiser

app = FastAPI(title="AI-Driven Construction Planner - Timeline Component")

class GenerateTimelineRequest(BaseModel):
    building_schema: Dict[str, Any]
    cost_report: Dict[str, Any]
    project_start_date: Optional[date] = None

class TimelineUpdate(BaseModel):
    # TODO: define the schema for updating timeline with actual progress
    completed_phases: list[str]

# Global instances for DI
preprocessor = Preprocessor()
feature_engineer = FeatureEngineer()
schedule_model = ScheduleModel()
critical_path_engine = CriticalPathEngine()
gantt_builder = GanttBuilder()
serialiser = TimelineSerialiser()

@app.post("/timeline/generate")
async def generate_timeline(req: GenerateTimelineRequest):
    """
    Generates a complete project schedule given building constraints and cost breakdown.
    """
    try:
        start_date = req.project_start_date or date.today()

        # Pipeline
        df_preprocessed = preprocessor.prepare(req.building_schema, req.cost_report)
        df_features = feature_engineer.build_features(df_preprocessed)
        
        phase_durations = schedule_model.predict_phase_durations(df_features)
        graph = critical_path_engine.build_network(phase_durations)
        critical_path_result = critical_path_engine.calculate(graph)
        
        gantt_data = gantt_builder.build(phase_durations, critical_path_result, start_date)
        
        timeline_json = serialiser.serialise(
            phase_durations, 
            critical_path_result, 
            gantt_data, 
            req.building_schema, 
            req.cost_report
        )

        # TODO: Save to PostgreSQL
        # ...

        return timeline_json
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/timeline/{project_id}")
async def get_timeline(project_id: str):
    """
    Returns the saved timeline for the specific project_id.
    """
    # TODO: Fetch from PostgreSQL
    return {"message": f"Timeline for {project_id} (Not implemented)"}

@app.post("/timeline/{project_id}/update")
async def update_timeline(project_id: str, update_data: TimelineUpdate):
    """
    Updates timeline with actual phase completion data.
    """
    # TODO: Update PostgreSQL record, push event, recalculate remaining
    return {"message": f"Updated timeline {project_id} (Not implemented)"}

@app.get("/timeline/{project_id}/gantt")
async def get_gantt(project_id: str):
    """
    Returns Gantt chart data structure for specific project.
    """
    # TODO: Fetch from PostgreSQL
    return {"message": f"Gantt data for {project_id} (Not implemented)"}

if __name__ == "__main__":
    import uvicorn
    # Use environment variables for configuration
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host=host, port=port)
