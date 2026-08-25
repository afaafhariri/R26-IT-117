# AI-Powered Construction Timeline Prediction and Project Management Model

## 1. Project Title

**AI-Powered Construction Timeline Prediction and Project Management Model**

This component is part of an AI-based construction planning and management system. It focuses on planned construction timeline prediction and project management schedule generation for residential building projects.

## 2. Student Details

| Field | Details |
|---|---|
| Student Name | Hanfi AMM |
| Student ID | IT22074454 |
| Component | Timeline Prediction and Project Management Model |
| Submission | PP1 Checklist 1 |

## 3. Component Overview

This component receives Cost Estimation JSON as input and predicts the planned construction schedule for a residential building project.

The component extracts BOQ, labour, building, and construction scope details from the Cost Estimation output. It then predicts phase-wise construction durations, total project duration, Gantt chart data, milestones, task dependencies, critical path, and a basic resource allocation plan.

The output is also converted into a planned schedule payload that can be sent to the Performance Monitoring and Delay Prediction Component.

## 4. Problem Addressed

Residential construction projects often need a planned timeline before construction begins. Manual schedule preparation can be inconsistent because it depends on project size, BOQ quantities, labour availability, phase dependencies, and the customer-selected construction scope.

This component solves that problem by generating a planned construction timeline from the Cost Estimation Component output.

## 5. System Workflow

```text
Cost Estimation Component JSON
        |
        v
AI-Powered Construction Timeline Prediction and Project Management Model
        |
        v
Timeline prediction + Gantt data + milestones + critical path + resources
        |
        v
Performance Monitoring and Delay Prediction Component
```

Main workflow:

1. Cost Estimation Component sends JSON output.
2. Timeline Component extracts BOQ, labour, building, and construction scope features.
3. XGBoost predicts phase-wise construction durations.
4. Random Forest is kept as a fallback model.
5. PyTorch LSTM predicts total duration from the construction phase sequence.
6. CPM logic generates task dependencies and critical path.
7. Gantt chart data and milestones are generated.
8. A planned schedule payload is created for the Performance Monitoring and Delay Prediction Component.

## 6. Input JSON Overview

The backend accepts Cost Estimation JSON containing fields such as:

- `estimate_id`
- `project_name`
- `planned_start_date`
- `summary`
- `boq_summary`
- `trade_breakdown`
- `risk_factors_applied`
- `model_metadata`
- `rate_metadata`
- `feeds_downstream`
- `construction_scope`

Important extracted features include:

- floor area
- built-up area
- number of floors
- room count
- bathroom count
- concrete quantity
- steel quantity
- brickwork quantity
- roof area
- electrical points
- plumbing fixtures
- labour count
- total labour days
- structural complexity score
- customer-selected construction scope

## 7. Output JSON Overview

The `/api/timeline/predict` endpoint returns:

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
- `construction_scope_summary`
- `performance_monitoring_payload`

The `performance_monitoring_payload` is the planned schedule payload sent to the Performance Monitoring and Delay Prediction Component.

## 8. Machine Learning Models

### Random Forest

Random Forest is used as the baseline and fallback model.

- Purpose: fallback phase duration prediction
- Model file: `models/timeline_random_forest_model.pkl`
- MAE: 1.9211 days
- RMSE: 3.0609
- R2: 0.8276
- MAPE: 6.97%

### XGBoost

XGBoost is the main model for phase-wise duration prediction.

- Purpose: main phase duration prediction model
- Model file: `models/timeline_xgboost_model.pkl`
- MAE: 1.4344 days
- RMSE: 2.2792
- R2: 0.8747
- MAPE: 5.48%

XGBoost is selected as the main model because it achieved the lowest MAE, RMSE, and MAPE compared with Random Forest.

### PyTorch LSTM

PyTorch LSTM is used for total project duration prediction from construction phase sequence data.

- Purpose: total duration sequence prediction
- Model file: `models/timeline_lstm_pytorch.pt`
- X scaler: `models/lstm_x_scaler.pkl`
- y scaler: `models/lstm_y_scaler.pkl`
- MAE: 14.4788 days
- RMSE: 18.7255
- R2: 0.9783
- MAPE: 5.94%

The LSTM uses the predicted construction phase duration sequence as input and predicts the total project duration.

## 9. Model Evaluation Results

| Model | Prediction Type | MAE | RMSE | R2 | MAPE |
|---|---|---:|---:|---:|---:|
| Random Forest | Phase duration prediction | 1.9211 days | 3.0609 | 0.8276 | 6.97% |
| XGBoost | Phase duration prediction | 1.4344 days | 2.2792 | 0.8747 | 5.48% |
| PyTorch LSTM | Total duration sequence prediction | 14.4788 days | 18.7255 | 0.9783 | 5.94% |

**Selected main model:** XGBoost  
**Reason:** XGBoost achieved the lowest MAE, RMSE, and MAPE for phase-wise construction duration prediction.

## 10. Dataset Details

The model was trained using a synthetic residential construction dataset.

Synthetic data was used because real residential house timeline data is difficult to collect and may be confidential. The dataset is suitable for prototype development and can be improved in the future using real residential construction project records.

Dataset features include:

- floor area
- built-up area
- number of floors
- room count
- bathroom count
- foundation excavation quantity
- foundation concrete quantity
- total concrete quantity
- steel quantity
- brickwork quantity
- roof area
- floor tile area
- wall plaster area
- paint area
- electrical points
- plumbing fixtures
- labour count
- total labour days
- structural complexity score
- phase-wise construction durations

## 11. Construction Scope Support

The system supports customer-selected construction scope.

Example:

A building design may contain 2 floors, and the Cost Estimation Component may calculate quantities for the full 2-floor building. However, the customer may want to construct only 1 floor at the current stage.

To handle this, the system separates:

- `planned_total_floors`
- `timeline_required_floors`

Example input:

```json
{
  "construction_scope": {
    "planned_total_floors": 2,
    "timeline_required_floors": 1,
    "scope_type": "partial_construction",
    "scope_description": "Customer wants to construct only ground floor at this stage"
  }
}
```

If `timeline_required_floors` is 1 and `planned_total_floors` is 2, the timeline is generated only for the selected 1-floor construction scope while keeping the full planned floor count for reference.

## 12. API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/` | Backend health check |
| POST | `/api/timeline/predict` | Generate full timeline prediction and project management output |
| POST | `/api/timeline/performance-format` | Generate planned schedule payload for the Performance Monitoring and Delay Prediction Component |

Swagger documentation:

```text
http://127.0.0.1:8000/docs
```

## 13. How to Run Backend

Open a terminal in the project root and run:

```bash
cd timeline
python -m uvicorn app.main:app --reload
```

Backend URL:

```text
http://127.0.0.1:8000
```

Swagger UI:

```text
http://127.0.0.1:8000/docs
```

## 14. How to Run Frontend Demo

The file `dashboard.html` is a PP1 demo frontend used to show:

- Cost Estimation JSON input
- Timeline prediction output
- Gantt chart visualization
- construction scope result
- performance monitoring payload

Run the frontend demo:

```bash
cd timeline
python -m http.server 5500
```

Open:

```text
http://127.0.0.1:5500/dashboard.html
```

## 15. Sample Input JSON

```json
{
  "estimate_id": "EST-DEMO-001",
  "planned_start_date": "2026-06-01",
  "project_name": "Two Storey Residential House",
  "district": "Colombo",
  "rate_metadata": {
    "district": "Colombo",
    "province": "Western"
  },
  "feeds_downstream": {
    "floor_area_sqm": 185.8,
    "built_up_area_sqft": 2000,
    "floors": 2,
    "room_count": 5,
    "bathroom_count": 3,
    "labour_count": 20,
    "total_labour_days": 780,
    "structural_complexity_score": 1.8,
    "building_type": "residential"
  },
  "construction_scope": {
    "planned_total_floors": 2,
    "timeline_required_floors": 1,
    "scope_type": "partial_construction",
    "scope_description": "Customer wants to construct only ground floor at this stage"
  },
  "boq_summary": {
    "structural": {
      "foundation_excavation_m3": 70,
      "foundation_concrete_m3": 35,
      "total_concrete_m3": 110,
      "steel_kg_estimate": 8500,
      "total_brickwork_m3": 80,
      "roof_area_sqm": 190
    },
    "finishing": {
      "floor_tile_sqm": 310,
      "wall_plaster_sqm": 920,
      "paint_sqm": 850
    },
    "services": {
      "electrical_points": 58,
      "total_plumbing_fixtures": 16
    },
    "aggregates": {}
  },
  "summary": {
    "total_estimated_cost": 6400000
  },
  "risk_factors_applied": {
    "multi_storey": true
  },
  "model_metadata": {
    "source_component": "cost_estimation"
  }
}
```

## 16. Sample Output Summary

The prediction response includes:

```json
{
  "project_id": "EST-DEMO-001",
  "project_name": "Two Storey Residential House",
  "total_project_duration_days": 123,
  "total_project_duration_weeks": 17.57,
  "model_predictions": {
    "phase_duration_model": "xgboost",
    "xgboost_status": "trained model used",
    "random_forest_status": "fallback available",
    "lstm_status": "trained PyTorch LSTM model used"
  },
  "construction_scope_summary": {
    "planned_total_floors": 2,
    "timeline_required_floors": 1,
    "scope_type": "partial_construction",
    "message": "Timeline generated for selected construction scope only"
  },
  "critical_path": [
    "foundation",
    "structure",
    "masonry",
    "plastering",
    "finishing",
    "painting",
    "handover"
  ],
  "gantt_chart_data": [],
  "milestones": [],
  "resource_allocation_plan": {},
  "performance_monitoring_payload": {}
}
```

## 17. Project Folder Structure

```text
timeline/
|
├── app/
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   ├── models/
│   │   └── schemas.py
│   ├── routes/
│   │   └── timeline_routes.py
│   ├── services/
│   │   ├── timeline_service.py
│   │   ├── random_forest_service.py
│   │   ├── lstm_service.py
│   │   ├── cpm_service.py
│   │   ├── gantt_service.py
│   │   ├── performance_format_service.py
│   │   └── resource_service.py
│   └── training/
│       ├── generate_synthetic_dataset.py
│       ├── train_random_forest.py
│       ├── train_xgboost.py
│       ├── train_lstm_pytorch.py
│       └── evaluate_models.py
├── data/
│   └── residential_timeline_dataset.csv
├── models/
│   ├── timeline_random_forest_model.pkl
│   ├── timeline_xgboost_model.pkl
│   ├── timeline_lstm_pytorch.pt
│   ├── lstm_x_scaler.pkl
│   └── lstm_y_scaler.pkl
├── dashboard.html
├── requirements.txt
├── Dockerfile
└── README.md
```

## 18. PP1 Completion Status

| Requirement | Status |
|---|---|
| Backend FastAPI service created | Completed |
| Cost Estimation JSON accepted as input | Completed |
| Feature extraction from BOQ and labour data | Completed |
| Synthetic residential dataset generated | Completed |
| Random Forest baseline/fallback model trained | Completed |
| XGBoost main phase-duration model trained | Completed |
| PyTorch LSTM total-duration model trained | Completed |
| Gantt chart data generation | Completed |
| Milestone generation | Completed |
| Task dependency generation | Completed |
| Critical path generation | Completed |
| Resource allocation plan generation | Completed |
| Construction scope support | Completed |
| Performance monitoring payload generation | Completed |
| PP1 demo frontend using `dashboard.html` | Completed |

## Future Improvements

- Improve the dataset using real residential project timeline records.
- Add more Sri Lankan district-wise productivity factors.
- Add weather and material availability factors using historical project data.
- Improve LSTM performance using real sequential construction schedules.
- Store generated predictions in a database for reporting and audit history.
