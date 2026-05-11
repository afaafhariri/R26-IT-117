"""Request and response schemas for construction timeline prediction."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


WeatherRisk = Literal["low", "medium", "high"]
MaterialAvailability = Literal["poor", "average", "good"]


class MaterialQuantities(BaseModel):
    cement_bags: float = Field(..., ge=0)
    steel_kg: float = Field(..., ge=0)
    bricks: float = Field(..., ge=0)
    sand_cubes: float = Field(..., ge=0)
    aggregate_cubes: float = Field(..., ge=0)
    tiles_sqft: float = Field(..., ge=0)
    paint_liters: float = Field(..., ge=0)


class LaborRequirements(BaseModel):
    masons: int = Field(..., ge=0)
    helpers: int = Field(..., ge=0)
    carpenters: int = Field(..., ge=0)
    electricians: int = Field(..., ge=0)
    plumbers: int = Field(..., ge=0)
    painters: int = Field(..., ge=0)


class PhaseWiseCost(BaseModel):
    foundation: float = Field(..., ge=0)
    structure: float = Field(..., ge=0)
    roofing: float = Field(..., ge=0)
    electrical_plumbing: float = Field(..., ge=0)
    finishing: float = Field(..., ge=0)


class ProjectConstraints(BaseModel):
    start_week: int = Field(1, ge=1)
    available_workers: int = Field(..., ge=1)
    weather_risk: WeatherRisk = "medium"
    material_availability: MaterialAvailability = "good"

    @field_validator("weather_risk", "material_availability", mode="before")
    @classmethod
    def normalize_enum_text(cls, value: str) -> str:
        return str(value).strip().lower()


class TimelinePredictionRequest(BaseModel):
    project_id: str = Field(..., min_length=1)
    project_name: str = Field(..., min_length=1)
    planned_start_date: str | None = None
    location: str = Field(..., min_length=1)
    built_up_area: float = Field(..., gt=0)
    number_of_floors: int = Field(..., gt=0)
    room_count: int = Field(..., gt=0)
    building_type: str = Field(..., min_length=1)
    foundation_type: str = Field(..., min_length=1)
    structural_type: str = Field(..., min_length=1)
    material_quantities: MaterialQuantities
    labor_requirements: LaborRequirements
    phase_wise_cost: PhaseWiseCost
    total_estimated_cost: float = Field(..., gt=0)
    project_constraints: ProjectConstraints


class TaskDependency(BaseModel):
    task: str
    depends_on: list[str]


class Milestone(BaseModel):
    name: str
    phase: str
    week: int


class GanttTask(BaseModel):
    id: int
    task: str
    start_date: str | None = None
    end_date: str | None = None
    start_week: float
    end_week: float
    duration_weeks: float
    duration_days: int | None = None


class ModelPredictions(BaseModel):
    phase_duration_model: str = "rule_based"
    xgboost_status: str = "not used"
    random_forest_status: str = "not used"
    lstm_status: str
    lstm_predicted_total_duration_days: int | None = None
    lstm_predicted_total_duration_weeks: float | None = None
    scheduled_total_duration_days: int | None = None
    scheduled_total_duration_weeks: float | None = None


class TimelinePredictionResponse(BaseModel):
    project_id: str
    project_name: str
    predicted_phase_durations_days: dict[str, int] | None = None
    predicted_phase_durations_weeks: dict[str, float]
    total_project_duration_days: int | None = None
    total_project_duration_weeks: float
    input_summary: dict[str, int | float | str | None] | None = None
    model_predictions: ModelPredictions
    task_dependencies: list[TaskDependency]
    critical_path: list[str]
    milestones: list[Milestone]
    gantt_chart_data: list[GanttTask]
    resource_allocation_plan: dict[str, dict]
    performance_monitoring_payload: dict[str, Any] | None = None
    confidence_score: float
    message: str

    model_config = ConfigDict(
        protected_namespaces=(),
        json_schema_extra={
            "example": {
                "project_id": "P001",
                "project_name": "Two Storey Residential House",
                "predicted_phase_durations_weeks": {
                    "foundation": 3,
                    "structure": 8,
                    "roofing": 2,
                    "electrical_plumbing": 4,
                    "finishing": 6,
                },
                "total_project_duration_weeks": 23,
                "model_predictions": {
                    "phase_duration_model": "xgboost",
                    "xgboost_status": "trained model used",
                    "random_forest_status": "trained model used",
                    "lstm_status": "trained PyTorch LSTM model used",
                    "lstm_predicted_total_duration_days": 161,
                    "lstm_predicted_total_duration_weeks": 23,
                    "scheduled_total_duration_days": 169,
                    "scheduled_total_duration_weeks": 24.14,
                },
                "task_dependencies": [
                    {"task": "foundation", "depends_on": []},
                    {"task": "structure", "depends_on": ["foundation"]},
                ],
                "critical_path": ["foundation", "structure", "roofing", "finishing"],
                "milestones": [],
                "gantt_chart_data": [],
                "resource_allocation_plan": {},
                "confidence_score": 0.82,
                "message": "Timeline prediction generated successfully",
            }
        }
    )
