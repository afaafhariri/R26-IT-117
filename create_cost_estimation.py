import os

files = {
    "cost-estimation/requirements.txt": """fastapi==0.104.1
uvicorn==0.24.0
pydantic==2.5.2
xgboost==2.0.2
tensorflow==2.15.0
shap==0.44.0
scikit-learn==1.3.2
pandas==2.1.3
numpy==1.26.2
pytest==7.4.3
psycopg2-binary==2.9.9
""",
    "cost-estimation/Dockerfile": """FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \\
    build-essential \\
    libpq-dev \\
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
""",
    "cost-estimation/main.py": """from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, Any

app = FastAPI(title="AI-Driven Construction Planner - Cost Estimation")

class BuildingSchema(BaseModel):
    footprint_sqm: float
    perimeter: float
    floors: int
    finish_grade: str
    district: str
    is_coastal: bool
    plot_area: float

@app.post("/estimate")
async def estimate(schema: BuildingSchema):
    # TODO: Integrate full 5-layer pipeline
    return {"status": "success", "message": "Cost Report JSON stub"}

@app.post("/boq")
async def boq(schema: BuildingSchema):
    # TODO: Integrate Layer 1 BOQ
    return {"status": "success", "message": "BOQ only stub"}

@app.get("/rates/{district}")
async def get_rates(district: str):
    # TODO: Integrate ICTAD rates
    return {"district": district, "rates": {}}

@app.post("/retrain")
async def retrain():
    # TODO: Model retraining logic
    return {"status": "success", "message": "Retraining triggered"}
""",
    "cost-estimation/layers/__init__.py": "",
    "cost-estimation/layers/layer1_boq/__init__.py": "",
    "cost-estimation/layers/layer1_boq/structural_boq.py": """class StructuralBOQ:
    def calculate(self, building_schema: dict) -> dict:
        perimeter = building_schema.get('perimeter', 0.0)
        footprint_sqm = building_schema.get('footprint_sqm', 0.0)
        
        return {
            "foundation_excavation_m3": perimeter * 1.5 * 0.6,
            "blinding_concrete_m3": perimeter * 0.6 * 0.05,
            "foundation_concrete_m3": perimeter * 0.6 * 0.45,
            "rc_slab_m3": footprint_sqm * 0.125,
            "roof_area_sqm": footprint_sqm * 1.30
        }
""",
    "cost-estimation/layers/layer1_boq/finishing_boq.py": """class FinishingBOQ:
    def calculate(self, building_schema: dict, finish_grade: str) -> dict:
        footprint_sqm = building_schema.get('footprint_sqm', 0.0)
        return {
            "floor_tile_sqm": footprint_sqm * 0.9,
            "wall_plaster_sqm": footprint_sqm * 2.5
        }
""",
    "cost-estimation/layers/layer1_boq/services_boq.py": """class ServicesBOQ:
    def calculate(self, rooms: dict) -> dict:
        return {"electrical_points": 20, "plumbing_fixtures": 5}
""",
    "cost-estimation/layers/layer1_boq/boq_engine.py": """class BOQEngine:
    pass
""",
    "cost-estimation/layers/layer2_rate_engine/__init__.py": "",
    "cost-estimation/layers/layer2_rate_engine/ictad_loader.py": """class ICTADLoader:
    pass
""",
    "cost-estimation/layers/layer2_rate_engine/district_multiplier.py": """class DistrictMultiplier:
    def __init__(self):
        self.multipliers = {
            "Colombo": 1.00,
            "Gampaha": 1.02,
            "Kandy": 1.05,
            "Ampara": 1.12,
            "Trincomalee": 1.14,
            "Vavuniya": 1.18,
            "Mullaitivu": 1.22
        }
    def get_multiplier(self, district: str) -> float:
        return self.multipliers.get(district, 1.0)
    def apply(self, base_rate: float, district: str) -> float:
        return base_rate * self.get_multiplier(district)
""",
    "cost-estimation/layers/layer2_rate_engine/price_escalation.py": """class PriceEscalationModel:
    def predict_escalation(self, base_rate: float, base_date: str, target_date: str) -> float:
        months = 1 # Stub
        return base_rate * (1 + 0.008 * months)
""",
    "cost-estimation/layers/layer2_rate_engine/rate_engine.py": """class RateEngine:
    pass
""",
    "cost-estimation/layers/layer3_ml_prediction/__init__.py": "",
    "cost-estimation/layers/layer3_ml_prediction/feature_engineer.py": """import pandas as pd
class FeatureEngineer:
    def build_features(self, boq, site_schema, finish_grade) -> pd.DataFrame:
        return pd.DataFrame()
""",
    "cost-estimation/layers/layer3_ml_prediction/xgboost_model.py": """class XGBoostCostModel:
    def train(self, X, y): pass
    def predict(self, X) -> float: return 0.0
    def predict_interval(self, X) -> tuple[float, float]: return (0.0, 0.0)
    def save(self, path): pass
    def load(self, path): pass
""",
    "cost-estimation/layers/layer3_ml_prediction/mlp_model.py": """class ResidualMLPModel:
    def train(self, X, y, epochs=100, patience=20): pass
    def predict(self, X) -> float: return 0.0
    def save(self, path): pass
    def load(self, path): pass
""",
    "cost-estimation/layers/layer3_ml_prediction/ensemble.py": """class EnsembleCostPredictor:
    def predict(self, X) -> dict: return {}
""",
    "cost-estimation/layers/layer3_ml_prediction/shap_explainer.py": """class SHAPExplainer:
    def explain(self, model, X) -> list[dict]: return []
""",
    "cost-estimation/layers/layer4_risk_adjuster/__init__.py": "",
    "cost-estimation/layers/layer4_risk_adjuster/risk_scorer.py": """class RiskScorer:
    def score(self, site_schema, building_schema, finish_grade) -> dict: return {"total_risk_pct": 0.10}
""",
    "cost-estimation/layers/layer4_risk_adjuster/contingency.py": """class ContingencyCalculator:
    def calculate(self, direct_cost, risk_pct) -> dict: return {}
""",
    "cost-estimation/layers/layer4_risk_adjuster/report_builder.py": """class ReportBuilder:
    def build(self, boq, rates, prediction, risk, contingency) -> dict: return {}
""",
    "cost-estimation/tests/__init__.py": "",
    "cost-estimation/tests/conftest.py": """import pytest
@pytest.fixture
def sample_building_schema():
    return {
        "footprint_sqm": 150.0,
        "perimeter": 50.0,
        "floors": 2,
        "finish_grade": "mid",
        "district": "Colombo"
    }
""",
    "cost-estimation/tests/test_boq.py": """def test_structural_boq(sample_building_schema): pass
def test_finishing_boq(sample_building_schema): pass
def test_services_boq(sample_building_schema): pass
""",
    "cost-estimation/tests/test_rate_engine.py": """def test_district_multiplier(): pass
def test_price_escalation(): pass
def test_rate_engine(): pass
""",
    "cost-estimation/tests/test_ensemble.py": """def test_ensemble_predict(): pass
def test_xgboost_train(): pass
def test_mlp_train(): pass
"""
}

for path, content in files.items():
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "w") as f:
        f.write(content)

print("Created cost-estimation files")
