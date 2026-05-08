import pickle
import numpy as np
import os

# ── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR        = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS_DIR      = os.path.join(BASE_DIR, "models")
CLASSIFIER_PATH = os.path.join(MODELS_DIR, "xgboost_classifier.json")
REGRESSOR_PATH  = os.path.join(MODELS_DIR, "xgboost_regressor.json")
ENCODERS_PATH   = os.path.join(MODELS_DIR, "label_encoders.pkl")

# ── Feature order (must exactly match training column order) ─────────────────
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

# ── Default values for optional fields ───────────────────────────────────────
# Derived from delay_data.csv averages
DEFAULTS = {
    "delay_category":      "Labour",
    "labour_availability": 0.67,
    "material_supply":     1,
    "weather_severity":    0.50,
    "cumulative_delay":    18,
}

# ── Lazy-loaded globals ───────────────────────────────────────────────────────
_classifier = None
_regressor  = None
_encoders   = None


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
    """
    Run delay risk classification and delay days regression.

    Required: phase_group, sub_phase, district, province, floors
    Optional: delay_category, labour_availability, material_supply,
              weather_severity, cumulative_delay  (defaults applied if None)

    Returns dict with risk_level, delay_days, confidence, risk_probabilities.
    """
    clf, reg, encoders = _load_models()

    # Apply defaults for optional fields
    delay_category      = delay_category      or DEFAULTS["delay_category"]
    labour_availability = labour_availability if labour_availability is not None else DEFAULTS["labour_availability"]
    material_supply     = material_supply     if material_supply     is not None else DEFAULTS["material_supply"]
    weather_severity    = weather_severity    if weather_severity    is not None else DEFAULTS["weather_severity"]
    cumulative_delay    = cumulative_delay    if cumulative_delay    is not None else DEFAULTS["cumulative_delay"]

    # ── Encode categoricals ───────────────────────────────────────────────────
    def safe_encode(encoder, value, field):
        if value not in encoder.classes_:
            raise ValueError(
                f"Unknown {field} value: '{value}'. "
                f"Valid options: {list(encoder.classes_)}"
            )
        return encoder.transform([value])[0]

    enc_phase_group    = safe_encode(encoders["phase_group"],    phase_group,    "phase_group")
    enc_sub_phase      = safe_encode(encoders["sub_phase"],      sub_phase,      "sub_phase")
    enc_district       = safe_encode(encoders["district"],       district,       "district")
    enc_province       = safe_encode(encoders["province"],       province,       "province")
    enc_delay_category = safe_encode(encoders["delay_category"], delay_category, "delay_category")

    # ── Build feature vector driven by FEATURES order ────────────────────────
    feature_values = {
        "phase_group":         enc_phase_group,
        "sub_phase":           enc_sub_phase,
        "district":            enc_district,
        "province":            enc_province,
        "floors":              int(floors),
        "delay_category":      enc_delay_category,
        "labour_availability": float(labour_availability),
        "material_supply":     int(material_supply),
        "weather_severity":    float(weather_severity),
        "cumulative_delay":    int(cumulative_delay),
    }
    assert list(feature_values.keys()) == FEATURES, \
        f"Feature order mismatch: {list(feature_values.keys())} != {FEATURES}"

    features = np.array([[feature_values[f] for f in FEATURES]])

    # ── Classifier: risk level + probabilities ────────────────────────────────
    risk_proba    = clf.predict_proba(features)[0]              # e.g. [p_HIGH, p_LOW, p_MEDIUM]
    risk_label_id = int(np.argmax(risk_proba))
    risk_classes  = list(encoders["delay_risk"].classes_)       # ['HIGH', 'LOW', 'MEDIUM']

    risk_level  = risk_classes[risk_label_id]
    confidence  = round(float(risk_proba[risk_label_id]) * 100, 2)

    risk_probabilities = {
        cls: round(float(prob), 4)
        for cls, prob in zip(risk_classes, risk_proba)
    }

    # ── Regressor: estimated delay days ──────────────────────────────────────
    delay_days = max(0, round(float(reg.predict(features)[0])))

    return {
        "risk_level":          risk_level,
        "delay_days":          delay_days,
        "confidence":          confidence,
        "risk_probabilities":  risk_probabilities,
    }
