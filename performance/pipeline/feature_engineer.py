import numpy as np

LABOUR_MAP = {
    "Very Low": 0.2,
    "Low": 0.4,
    "Medium": 0.6,
    "Good": 0.8,
    "Full": 1.0,
}

MATERIAL_MAP = {
    "Yes": 1,
    "No": 0,
}

WEATHER_MAP = {
    "No disruption": 0.1,
    "Minor": 0.3,
    "Moderate": 0.6,
    "Severe": 0.9,
}


def map_labour_availability(label: str) -> float:
    if label not in LABOUR_MAP:
        raise ValueError(f"Invalid labour_availability: {label}")
    return LABOUR_MAP[label]


def map_material_supply(label: str) -> int:
    if label not in MATERIAL_MAP:
        raise ValueError(f"Invalid material_supply: {label}")
    return MATERIAL_MAP[label]


def map_weather_severity(label: str) -> float:
    if label not in WEATHER_MAP:
        raise ValueError(f"Invalid weather_severity: {label}")
    return WEATHER_MAP[label]


def validate_feature_context(context: dict) -> None:
    required_fields = [
        "phase_group",
        "sub_phase",
        "district",
        "province",
        "floors",
        "delay_category",
        "labour_availability_score",
        "material_supply_score",
        "weather_severity_score",
        "cumulative_delay",
    ]
    missing = [f for f in required_fields if f not in context or context.get(f) is None]
    if missing:
        raise ValueError(f"Missing required feature context fields: {missing}")


def merge_db_context_with_assessment(db_context: dict, assessment_payload: dict, cumulative_delay: int) -> dict:
    context = {
        "phase_group": db_context["phase_group"],
        "sub_phase": db_context["sub_phase"],
        "district": db_context["district"],
        "province": db_context["province"],
        "floors": db_context["floors"],
        "delay_category": assessment_payload["delay_category"],
        "labour_availability_score": map_labour_availability(assessment_payload["labour_availability"]),
        "material_supply_score": map_material_supply(assessment_payload["material_supply"]),
        "weather_severity_score": map_weather_severity(assessment_payload["weather_severity"]),
        "cumulative_delay": int(cumulative_delay),
    }
    validate_feature_context(context)
    return context


def build_feature_matrix(
    feature_order: list[str],
    *,
    enc_phase_group: int,
    enc_sub_phase: int,
    enc_district: int,
    enc_province: int,
    floors: int,
    enc_delay_category: int,
    labour_availability: float,
    material_supply: int,
    weather_severity: float,
    cumulative_delay: int,
) -> np.ndarray:
    feature_values = {
        "phase_group": enc_phase_group,
        "sub_phase": enc_sub_phase,
        "district": enc_district,
        "province": enc_province,
        "floors": floors,
        "delay_category": enc_delay_category,
        "labour_availability": labour_availability,
        "material_supply": material_supply,
        "weather_severity": weather_severity,
        "cumulative_delay": cumulative_delay,
    }

    if list(feature_values.keys()) != feature_order:
        raise ValueError(
            f"Feature order mismatch: {list(feature_values.keys())} != {feature_order}"
        )

    return np.array([[feature_values[f] for f in feature_order]], dtype=float)


def build_encoded_feature_payload(context: dict, encoders: dict, feature_order: list[str]) -> np.ndarray:
    validate_feature_context(context)

    def safe_encode(field_name: str, value: str) -> int:
        encoder = encoders[field_name]
        if value not in encoder.classes_:
            raise ValueError(
                f"Unknown {field_name} value: '{value}'. Valid options: {list(encoder.classes_)}"
            )
        return int(encoder.transform([value])[0])

    try:
        floors = int(context["floors"])
        labour = float(context["labour_availability_score"])
        material = int(context["material_supply_score"])
        weather = float(context["weather_severity_score"])
        cumulative = int(context["cumulative_delay"])
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid numeric feature type for ML prediction.") from exc

    if floors < 1 or floors > 3:
        raise ValueError("Invalid floors value: floors must be between 1 and 3.")
    if labour < 0 or labour > 1:
        raise ValueError("Invalid labour_availability score: must be between 0.0 and 1.0.")
    if material not in (0, 1):
        raise ValueError("Invalid material_supply score: must be 0 or 1.")
    if weather < 0 or weather > 1:
        raise ValueError("Invalid weather_severity score: must be between 0.0 and 1.0.")

    return build_feature_matrix(
        feature_order,
        enc_phase_group=safe_encode("phase_group", context["phase_group"]),
        enc_sub_phase=safe_encode("sub_phase", context["sub_phase"]),
        enc_district=safe_encode("district", context["district"]),
        enc_province=safe_encode("province", context["province"]),
        floors=floors,
        enc_delay_category=safe_encode("delay_category", context["delay_category"]),
        labour_availability=labour,
        material_supply=material,
        weather_severity=weather,
        cumulative_delay=cumulative,
    )
