"""Contract tests for the C02 -> C03 feature handoff.

C03 consumes C02's cost report as a loosely-typed dict, reading values by key
with silent numeric defaults. That design has produced the same class of bug
more than once: a field C02 never sends (floors) quietly becomes a default, and
a field C02 sends on a *different scale* (structural_complexity_score, a 0-1
concrete ratio, versus the 1.1-2.674 multiplier the model was fitted on) is
quietly used anyway.

Both failures are invisible at runtime - the prediction still returns 200 with
plausible-looking numbers. These tests pin the invariant that actually matters:
every value handed to the model must lie inside the range that model was
trained on.
"""

import sys
from pathlib import Path

import pytest

TIMELINE_ROOT = Path(__file__).resolve().parents[1]
if str(TIMELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(TIMELINE_ROOT))

from app.services.random_forest_service import (  # noqa: E402
    INPUT_FEATURES,
    LEGACY_COMPLEXITY_RANGE,
    XGBOOST_MODEL_PATH,
    build_feature_vector,
    load_xgboost_model,
)

TRAINING_CSV = TIMELINE_ROOT / "data" / "residential_timeline_dataset.csv"


@pytest.fixture
def c02_report() -> dict:
    """A C02 /estimate response, trimmed to the parts C03 reads.

    Values are from a real run for a two-storey, 220 sqm Colombo house. Note
    feeds_downstream.structural_complexity_score is 0.725 - C02's own 0-1
    quantity, not the feature the timeline model was trained on.
    """

    return {
        "summary": {"total_lkr": 15455266.61, "cost_per_sqm_lkr": 70251.21},
        "boq_summary": {
            "structural": {
                "foundation_excavation_m3": 39.6,
                "foundation_concrete_m3": 11.88,
                "rc_columns_m3": 3.809,
                "rc_slab_m3": 27.5,
                "roof_area_sqm": 143.0,
            },
            "finishing": {
                "floor_tile_sqm": 198.0,
                "wall_plaster_sqm": 528.0,
                "paint_sqm": 484.0,
            },
            "services": {"electrical_points": 49, "total_plumbing_fixtures": 12},
            "aggregates": {
                "total_concrete_m3": 44.509,
                "steel_kg_estimate": 4896.0,
                "total_brickwork_m3": 95.68,
                "floor_area_sqm": 220.0,
            },
        },
        "rate_metadata": {"district": "Colombo", "province": "Western"},
        "feeds_downstream": {
            "total_labour_days": 1320,
            "structural_complexity_score": 0.725,
            "floor_area_sqm": 220.0,
            "floors": 2,
            "bathroom_count": 3,
        },
    }


def _training_ranges() -> dict[str, tuple[float, float]] | None:
    """Ranges the live model was fitted on, from the package or the dataset."""

    package = load_xgboost_model()
    if package and package.get("feature_ranges"):
        return {k: tuple(v) for k, v in package["feature_ranges"].items()}

    if TRAINING_CSV.exists():
        import pandas as pd

        df = pd.read_csv(TRAINING_CSV)
        return {
            name: (float(df[name].min()), float(df[name].max()))
            for name in INPUT_FEATURES
            if name in df.columns
        }
    return None


def test_complexity_lands_inside_the_trained_band(c02_report):
    """The contract this module exists to protect.

    C02 sends 0.725 (its 0-1 concrete ratio) under the same key as the model's
    1.1-2.674 complexity multiplier. Before the guard, that was clamped to a
    constant 1.0 - below the entire training range - so the feature carried no
    information at all. This test fails on that pre-fix behaviour.
    """

    ranges = _training_ranges()
    if not ranges or "structural_complexity_score" not in ranges:
        pytest.skip("no trained range available for structural_complexity_score")

    low, high = ranges["structural_complexity_score"]
    score = build_feature_vector(c02_report, ranges)["structural_complexity_score"]

    assert low <= score <= high, (
        f"structural_complexity_score={score:.4f} outside trained "
        f"[{low:.4f}, {high:.4f}] - the feature is not carrying signal"
    )


def test_no_feature_is_wildly_outside_its_trained_range(c02_report):
    """A loose scale check across every feature, to catch unit errors - sqft
    fed into a sqm feature, a ratio fed into a multiplier.

    Deliberately generous: C03's model is trained on a *synthetic* dataset, so
    real C02 quantities can legitimately sit just outside its span without
    anything being wrong. foundation_concrete_m3 for a small house is a known
    example (11.88 against a training floor of 12.02). Only excursions beyond
    half the range span in either direction are treated as scale errors.

    This is the blunt net; test_complexity_lands_inside_the_trained_band is the
    precise one. Note it does NOT catch the historical floors bug - floors was
    pinned to 1, which sits inside the trained 1-3 range. That is what
    test_floors_survives_the_c02_handoff is for.
    """

    ranges = _training_ranges()
    if not ranges:
        pytest.skip("no feature_ranges on the model package and no training CSV")

    features = build_feature_vector(c02_report, ranges)

    wild = {}
    for name, (low, high) in ranges.items():
        if name not in features:
            continue
        margin = 0.5 * (high - low)
        if not (low - margin) <= features[name] <= (high + margin):
            wild[name] = (features[name], low, high)

    assert not wild, "features at an implausible scale: " + "; ".join(
        f"{n}={v:.4f} far outside [{lo:.4f}, {hi:.4f}]" for n, (v, lo, hi) in wild.items()
    )


def test_floors_survives_the_c02_handoff(c02_report):
    """C02 must keep sending floors. It was dropped once, which silently made
    every downstream project single-storey - including C04's project record,
    where floors is one of only ten delay-model features."""

    assert build_feature_vector(c02_report)["num_floors"] == 2.0

    without = {**c02_report, "feeds_downstream": {
        k: v for k, v in c02_report["feeds_downstream"].items() if k != "floors"
    }}
    assert build_feature_vector(without)["num_floors"] == 1.0, (
        "no floors anywhere in the payload should fall back to 1"
    )


def test_c02s_ratio_scale_complexity_is_not_fed_to_the_model(c02_report):
    """C02 publishes a 0-1 concrete ratio under the same key as the model's
    1.1-2.674 complexity multiplier. It must not reach the model as-is."""

    score = build_feature_vector(c02_report)["structural_complexity_score"]

    assert score != c02_report["feeds_downstream"]["structural_complexity_score"]
    low, high = LEGACY_COMPLEXITY_RANGE
    assert low <= score <= high


def test_guard_self_corrects_if_the_model_is_retrained_on_the_ratio_scale(c02_report):
    """The guard is pinned to the model, not to a constant. If someone retrains
    on a dataset whose complexity really is C02's 0-1 ratio, the recorded range
    moves with it and C02's value must then be used verbatim.

    If this test fails, the guard has become a hardcoded assumption again."""

    retrained = {"structural_complexity_score": (0.0, 1.0)}
    score = build_feature_vector(c02_report, retrained)["structural_complexity_score"]

    assert score == 0.725, (
        "a model retrained on the 0-1 ratio must receive C02's value unchanged"
    )


def test_malformed_feature_ranges_fall_back_safely(c02_report):
    """A corrupt or partial package must not take the service down."""

    for bad in ({"structural_complexity_score": "garbage"},
                {"structural_complexity_score": (5.0, 5.0)},
                {}):
        score = build_feature_vector(c02_report, bad)["structural_complexity_score"]
        low, high = LEGACY_COMPLEXITY_RANGE
        assert low <= score <= high


def test_model_package_records_feature_ranges():
    """Retraining should record the ranges. Skips (rather than fails) on the
    currently committed artifact, which predates this - it starts passing the
    first time train_xgboost.py is re-run."""

    package = load_xgboost_model()
    if package is None:
        pytest.skip(f"no model at {XGBOOST_MODEL_PATH}")
    if "feature_ranges" not in package:
        pytest.skip("committed model predates feature_ranges; re-run train_xgboost.py")

    assert set(package["feature_ranges"]) == set(package["input_features"])
