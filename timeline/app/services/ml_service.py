"""Rule-based baseline model for construction phase duration prediction."""

from app.models.schemas import TimelinePredictionRequest


PHASE_ORDER = [
    "foundation",
    "structure",
    "roofing",
    "electrical_plumbing",
    "finishing",
]


def predict_phase_durations_rule_based(
    request: TimelinePredictionRequest,
) -> dict[str, int]:
    """
    Predict phase durations using transparent baseline rules.

    This prototype model is intentionally simple. Later, this function can be
    replaced by a trained Random Forest, XGBoost, or neural network model while
    keeping the same return structure.
    """

    durations = {
        "foundation": 2,
        "structure": 4,
        "roofing": 2,
        "electrical_plumbing": 3,
        "finishing": 4,
    }

    area = request.built_up_area
    floors = request.number_of_floors
    rooms = request.room_count
    material = request.material_quantities
    labor = request.labor_requirements
    constraints = request.project_constraints

    # Larger houses need longer foundation and structural work.
    if area > 1500:
        durations["foundation"] += 1
        durations["structure"] += 2
    if area > 2500:
        durations["foundation"] += 1
        durations["structure"] += 3
        durations["finishing"] += 1

    # Extra floors mainly affect structural frame duration.
    if floors > 1:
        durations["structure"] += 2 * (floors - 1)
        durations["roofing"] += 1 if floors >= 3 else 0

    # More rooms usually means more finishes and more MEP points.
    if rooms > 4:
        durations["finishing"] += 1
        durations["electrical_plumbing"] += 1
    if rooms > 8:
        durations["finishing"] += 1

    # High material quantities increase the relevant phase durations.
    if material.cement_bags > 700 or material.steel_kg > 3500:
        durations["foundation"] += 1
        durations["structure"] += 1
    if material.bricks > 18000:
        durations["structure"] += 1
    if material.tiles_sqft > 1800 or material.paint_liters > 250:
        durations["finishing"] += 1

    # Foundation and roofing are sensitive to weather.
    if constraints.weather_risk == "high":
        durations["foundation"] += 1
        durations["roofing"] += 1

    # Poor material availability slows all major phases.
    if constraints.material_availability == "poor":
        for phase in PHASE_ORDER:
            durations[phase] += 1
    elif constraints.material_availability == "average":
        durations["structure"] += 1
        durations["finishing"] += 1

    # Low available workers increase phase durations slightly.
    required_workers = (
        labor.masons
        + labor.helpers
        + labor.carpenters
        + labor.electricians
        + labor.plumbers
        + labor.painters
    )
    available_workers = constraints.available_workers
    if available_workers < 12:
        for phase in PHASE_ORDER:
            durations[phase] += 1
    elif available_workers < max(required_workers * 0.75, 1):
        durations["structure"] += 1
        durations["finishing"] += 1

    return {phase: max(1, int(round(weeks))) for phase, weeks in durations.items()}


def estimate_confidence_score(request: TimelinePredictionRequest) -> float:
    """
    Return a simple confidence score for the prototype baseline model.

    Clean inputs with good material availability and enough labour produce a
    higher score. High-risk conditions lower confidence.
    """

    score = 0.84
    constraints = request.project_constraints

    if request.built_up_area > 3000:
        score -= 0.04
    if request.number_of_floors > 2:
        score -= 0.03
    if constraints.weather_risk == "high":
        score -= 0.05
    if constraints.material_availability == "poor":
        score -= 0.06
    if constraints.available_workers < 12:
        score -= 0.04
    if constraints.material_availability == "good":
        score += 0.02

    return round(min(max(score, 0.60), 0.92), 2)
