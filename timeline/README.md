# Project Management & Timeline Prediction Backend

Student: Hanfi A.M.M | IT22074454 | SLIIT  
Project: AI-Based Intelligent Construction Planning and Management System  
Component: Project Management & Timeline Prediction Model

## Component Description

The Project Management & Timeline Prediction Model receives Cost Estimation Component JSON as input and predicts the planned construction timeline. It uses XGBoost for phase-wise duration prediction and PyTorch LSTM for total duration prediction. It generates project management planning outputs such as Gantt chart data, milestones, critical path, task dependencies, and basic resource allocation. It also creates a planned schedule payload for the Performance Monitoring & Delay Prediction Component.

This component creates the planned schedule baseline. It does not perform cost estimation, actual site construction monitoring, delay prediction, progress tracking, or delay risk analysis.

## System Integration Flow

```text
Cost Estimation Component JSON
        ↓
Project Management & Timeline Prediction Model
        ↓
Timeline forecasting + construction scheduling + resource allocation
        ↓
Performance monitoring payload
        ↓
Performance Monitoring & Delay Prediction Component
```

The Architecture Planning Component sends building data to the Cost Estimation Component. The Cost Estimation Component sends BOQ, cost, labour, rate, and downstream feature JSON to this Timeline Component. This Timeline Component returns planned phase durations, total planned duration, project management planning outputs, and a downstream planned schedule payload.

## Scope

### In Scope

1. Receive Cost Estimation JSON
2. Feature extraction from BOQ and cost estimation output
3. Timeline forecasting
4. Phase duration prediction using XGBoost
5. Total duration prediction using PyTorch LSTM
6. Labour count adjustment
7. Construction scheduling
8. Gantt chart data generation
9. Milestone generation
10. Critical path identification
11. Task dependency generation
12. Basic resource allocation plan
13. Planned schedule payload generation for downstream monitoring component

### Out of Scope

1. Cost estimation
2. Actual site construction monitoring
3. Delay prediction
4. Progress tracking
5. Real-time performance monitoring
6. Delay risk analysis
7. Actual site image/report analysis
8. Procurement/material tracking
9. Cash flow/payment planning

## Backend Setup

Create and activate a Python virtual environment inside the `timeline` folder.

```bash
cd timeline
python -m venv .venv
.venv\Scripts\activate
```

For macOS/Linux:

```bash
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Run the backend:

```bash
python -m uvicorn app.main:app --reload
```

Swagger UI:

```text
http://127.0.0.1:8000/docs
```

## API Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/` | Health check |
| POST | `/api/timeline/predict` | Returns the full timeline planning output for this component |
| POST | `/api/timeline/performance-format` | Returns only the planned schedule JSON required by the downstream component |

Health response:

```json
{
  "message": "Project Management & Timeline Prediction Backend is running"
}
```

## Input From Cost Estimation Component

The main input is the Cost Estimation Component JSON. It can include fields such as:

- `estimate_id`
- `summary`
- `boq_summary`
- `trade_breakdown`
- `risk_factors_applied`
- `model_metadata`
- `rate_metadata`
- `feeds_downstream`
- `planned_start_date`

The backend extracts these timeline features when available:

- `foundation_excavation_m3`
- `foundation_concrete_m3`
- `total_concrete_m3`
- `steel_kg_estimate`
- `total_brickwork_m3`
- `roof_area_sqm`
- `floor_tile_sqm`
- `wall_plaster_sqm`
- `paint_sqm`
- `electrical_points`
- `total_plumbing_fixtures`
- `total_labour_days`
- `labour_count`
- `structural_complexity_score`
- `floor_area_sqm`
- `bathroom_count`
- `district`
- `province`
- `floors`
- `building_type`
- `planned_start_date`

Safe defaults are applied when upstream fields are missing:

- `project_name = "Residential Construction Project"`
- `planned_start_date = current date`
- `building_type = "residential"`
- `floors = top-level floors, else feeds_downstream.floors, else 2 when risk_factors_applied.multi_storey exists, else 1`
- `labour_count = 20`
- `province = rate_metadata.province if available, else "Unknown"`
- `district = top-level district, else rate_metadata.district, else "Unknown"`

## `/api/timeline/predict`

Returns the full output for this component:

- `predicted_phase_durations_days`
- `predicted_phase_durations_weeks`
- `total_project_duration_days`
- `total_project_duration_weeks`
- `model_predictions`
- `task_dependencies`
- `critical_path`
- `milestones`
- `gantt_chart_data`
- `resource_allocation_plan`
- `input_summary`
- `performance_monitoring_payload`

Example response shape:

```json
{
  "project_id": "EST-001",
  "project_name": "Residential Construction Project",
  "predicted_phase_durations_days": {
    "foundation": 29,
    "structure": 46,
    "masonry": 21,
    "roofing": 16,
    "electrical": 13,
    "plumbing": 11,
    "plastering": 18,
    "finishing": 20,
    "painting": 14,
    "external_work": 12,
    "handover": 4,
    "raw_model_total_duration_days": 160
  },
  "predicted_phase_durations_weeks": {
    "foundation": 4.14,
    "structure": 6.57,
    "masonry": 3.0,
    "roofing": 2.29,
    "electrical": 1.86,
    "plumbing": 1.57,
    "plastering": 2.57,
    "finishing": 2.86,
    "painting": 2.0,
    "external_work": 1.71,
    "handover": 0.57
  },
  "total_project_duration_days": 153,
  "total_project_duration_weeks": 21.86,
  "model_predictions": {
    "phase_duration_model": "xgboost",
    "xgboost_status": "trained model used",
    "random_forest_status": "fallback available",
    "lstm_status": "trained PyTorch LSTM model used",
    "lstm_predicted_total_duration_days": 151,
    "lstm_predicted_total_duration_weeks": 21.57,
    "scheduled_total_duration_days": 153,
    "scheduled_total_duration_weeks": 21.86
  },
  "task_dependencies": [],
  "critical_path": [],
  "milestones": [],
  "gantt_chart_data": [],
  "resource_allocation_plan": {},
  "input_summary": {
    "labour_count": 20,
    "total_labour_days": 780,
    "structural_complexity_score": 1.8,
    "floor_area_sqm": 185.8,
    "labour_adjustment_applied": "no adjustment"
  },
  "performance_monitoring_payload": {},
  "confidence_score": 0.88,
  "message": "Timeline prediction generated successfully"
}
```

## `/api/timeline/performance-format`

Returns only the JSON required by the Performance Monitoring & Delay Prediction Component.

```json
{
  "project_id": "EST-001",
  "project_name": "Residential Construction Project",
  "district": "Colombo",
  "province": "Western",
  "floors": 2,
  "building_type": "residential",
  "total_planned_duration_days": 204,
  "planned_start_date": "2026-06-01",
  "planned_end_date": "2026-12-21",
  "phases": [
    {
      "phase_id": 1,
      "phase_group": "Foundations",
      "sub_phase": "Foundation work",
      "planned_start": "2026-06-01",
      "planned_end": "2026-06-29",
      "planned_duration_days": 29,
      "sequence": 1
    }
  ]
}
```

This payload is a planned schedule support contract for the next component. The next component can use it as its baseline input.

## Model Status

A synthetic residential construction dataset was generated for initial timeline model development.

Random Forest training summary:

- Dataset size: 1000 synthetic residential construction records
- Model: Random Forest Regressor
- Model path: `models/timeline_random_forest_model.pkl`
- MAE: 1.9211 days
- R2 score: 0.8276

XGBoost training summary:

- Dataset size: 1000 synthetic residential construction records
- Model: XGBoost Regressor with MultiOutputRegressor
- Model path: `models/timeline_xgboost_model.pkl`
- MAE: 1.4344 days
- R2 score: 0.8747

XGBoost is selected as the main phase-duration model because it has lower MAE and higher R2 than Random Forest. Random Forest remains available as the trained fallback model if the XGBoost file is missing or prediction fails.

PyTorch LSTM training summary:

- Dataset size: 1000 synthetic residential construction records
- Model: PyTorch LSTM sequence model
- Model path: `models/timeline_lstm_pytorch.pt`
- X scaler path: `models/lstm_x_scaler.pkl`
- y scaler path: `models/lstm_y_scaler.pkl`
- MAE: 14.4788 days
- R2 score: 0.9783

TensorFlow failed to load in the Windows environment, so PyTorch was used for the LSTM implementation. XGBoost predicts individual phase durations. The PyTorch LSTM receives the predicted phase sequence and predicts total project duration.

## Feature Extraction and Model Flow

The API first checks whether the incoming request is Cost Estimation Component output. If it contains fields such as `boq_summary`, `feeds_downstream`, `summary`, or `risk_factors_applied`, the backend extracts the trained model feature vector and uses the XGBoost model. If XGBoost is unavailable or fails, the backend falls back to Random Forest. If both trained models fail, the rule-based model is still available as the final fallback.

The trained model feature order is:

- `num_floors`
- `floor_area_sqm`
- `built_up_area_sqft`
- `room_count`
- `bathroom_count`
- `foundation_excavation_m3`
- `foundation_concrete_m3`
- `total_concrete_m3`
- `steel_kg_estimate`
- `total_brickwork_m3`
- `roof_area_sqm`
- `floor_tile_sqm`
- `wall_plaster_sqm`
- `paint_sqm`
- `electrical_points`
- `total_plumbing_fixtures`
- `total_labour_days`
- `structural_complexity_score`

The XGBoost model predicts:

- `foundation_days`
- `structure_days`
- `masonry_days`
- `roofing_days`
- `electrical_days`
- `plumbing_days`
- `plastering_days`
- `finishing_days`
- `painting_days`
- `external_work_days`
- `handover_days`
- `total_duration_days`

After phase prediction, the service applies the labour count adjustment:

- Missing labour count: no duration adjustment, default shown as `20`
- Less than 12 labourers: phase durations increase by 10%
- 12 to 24 labourers: no adjustment
- More than 24 labourers: phase durations reduce by 5%

The adjusted phase durations are used for PyTorch LSTM total duration prediction, Gantt chart data, milestones, critical path, task dependencies, and the downstream planned schedule payload.

## PyTorch LSTM Explanation

`app/services/lstm_service.py` contains the PyTorch LSTM runtime prediction logic.

The LSTM accepts the predicted phase durations in this sequence:

- `foundation_days`
- `structure_days`
- `masonry_days`
- `roofing_days`
- `electrical_days`
- `plumbing_days`
- `plastering_days`
- `finishing_days`
- `painting_days`
- `external_work_days`
- `handover_days`

The sequence is scaled using `lstm_x_scaler.pkl`, reshaped to `(1, 11, 1)`, passed into the PyTorch LSTM, and inverse-transformed using `lstm_y_scaler.pkl`. If LSTM loading or prediction fails, the API does not crash; it returns the scheduled construction duration as a fallback and sets `lstm_status` to `"fallback - LSTM prediction failed"`.

## Future Improvements

- Store historical project schedules in SQLite or PostgreSQL.
- Improve phase-duration models using real project schedule records.
- Improve the PyTorch LSTM model using real historical schedules.
- Add district-wise productivity and weather factors for planned schedule forecasting.
- Add confidence intervals using validation error or ensemble uncertainty.
- Add API endpoint for saving prediction records to the database.

## Docker

Build:

```bash
docker build -t timeline-backend .
```

Run:

```bash
docker run -p 8000:8000 timeline-backend
```
