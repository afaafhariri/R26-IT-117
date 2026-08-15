import os
import pickle
import numpy as np

from pipeline.feature_engineer import build_encoded_feature_payload

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS_DIR = os.path.join(BASE_DIR, "models")
CLASSIFIER_PATH = os.path.join(MODELS_DIR, "xgboost_classifier.json")
REGRESSOR_PATH = os.path.join(MODELS_DIR, "xgboost_regressor.json")
ENCODERS_PATH = os.path.join(MODELS_DIR, "label_encoders.pkl")

FEATURES = [
    "phase_group",
    "sub_phase",
    "district",
    "province",
    "floors",
    "delay_category",
    "labour_availability",
    "material_supply",
    "weather_severity",
    "cumulative_delay",
]

_classifier = None
_regressor = None
_encoders = None


def _load_models():
    global _classifier, _regressor, _encoders
    if _classifier is None:
        from xgboost import XGBClassifier, XGBRegressor

        _classifier = XGBClassifier()
        _classifier.load_model(CLASSIFIER_PATH)

        _regressor = XGBRegressor()
        _regressor.load_model(REGRESSOR_PATH)

        with open(ENCODERS_PATH, "rb") as f:
            _encoders = pickle.load(f)
    return _classifier, _regressor, _encoders


def predict_from_context(context: dict) -> dict:
    clf, reg, encoders = _load_models()
    features = build_encoded_feature_payload(context, encoders, FEATURES)

    risk_proba = clf.predict_proba(features)[0]
    risk_label_id = int(np.argmax(risk_proba))
    risk_classes = list(encoders["delay_risk"].classes_)
    risk_level = risk_classes[risk_label_id]
    confidence = round(float(risk_proba[risk_label_id]) * 100, 2)

    risk_probabilities = {
        cls: round(float(prob), 4) for cls, prob in zip(risk_classes, risk_proba)
    }
    delay_days = max(0, round(float(reg.predict(features)[0])))

    return {
        "risk_level": risk_level,
        "delay_days": delay_days,
        "confidence": confidence,
        "risk_probabilities": risk_probabilities,
    }


def predict(
    phase_group,
    sub_phase,
    district,
    province,
    floors,
    delay_category=None,
    labour_availability=None,
    material_supply=None,
    weather_severity=None,
    cumulative_delay=None,
):
    context = {
        "phase_group": phase_group,
        "sub_phase": sub_phase,
        "district": district,
        "province": province,
        "floors": floors,
        "delay_category": delay_category,
        "labour_availability_score": labour_availability,
        "material_supply_score": material_supply,
        "weather_severity_score": weather_severity,
        "cumulative_delay": cumulative_delay,
    }
    return predict_from_context(context)
