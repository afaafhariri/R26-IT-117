"""
Generate a synthetic residential construction timeline dataset.

This script creates 1000 Sri Lankan-style residential project records for the
timeline prediction component. It is a data generation utility only; it does
not train any machine learning model.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


SEED = 42
N_RECORDS = 1000

BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"
OUTPUT_PATH = DATA_DIR / "residential_timeline_dataset.csv"


def clamp(value: float, minimum: float, maximum: float) -> float:
    """Keep a numeric value inside a realistic range."""

    return max(minimum, min(value, maximum))


def positive_int(value: float, minimum: int = 1) -> int:
    """Round a generated duration to a positive integer day count."""

    return max(minimum, int(round(value)))


def generate_record(index: int, rng: np.random.Generator) -> dict:
    """Generate one synthetic residential construction project record."""

    num_floors = int(rng.integers(1, 4))
    floor_area_sqm = round(float(rng.uniform(80, 400)), 2)
    built_up_area_sqft = round(floor_area_sqm * 10.7639, 2)

    area_factor = floor_area_sqm / 100.0
    floor_factor = 1.0 + (num_floors - 1) * 0.42

    room_count = int(clamp(rng.normal(2.2 + area_factor * 1.25 + num_floors * 0.7, 1.0), 2, 8))
    bathroom_count = int(clamp(rng.normal(1.0 + num_floors * 0.65 + room_count * 0.18, 0.55), 1, 5))
    finish_grade = int(rng.choice([1, 2, 3], p=[0.34, 0.46, 0.20]))

    # Quantity estimates scale with area and floors, plus small variation.
    foundation_excavation_m3 = round(
        floor_area_sqm * (0.28 + 0.08 * num_floors) * rng.normal(1.0, 0.06),
        2,
    )
    foundation_concrete_m3 = round(
        floor_area_sqm * (0.12 + 0.04 * num_floors) * rng.normal(1.0, 0.05),
        2,
    )
    total_concrete_m3 = round(
        (foundation_concrete_m3 + floor_area_sqm * num_floors * 0.18)
        * rng.normal(1.0, 0.05),
        2,
    )
    steel_kg_estimate = round(
        floor_area_sqm * num_floors * (28 + 7 * num_floors) * rng.normal(1.0, 0.06),
        2,
    )
    total_brickwork_m3 = round(
        floor_area_sqm * num_floors * (0.18 + room_count * 0.012) * rng.normal(1.0, 0.06),
        2,
    )
    roof_area_sqm = round(
        floor_area_sqm * (1.05 + rng.uniform(0.03, 0.18)) * rng.normal(1.0, 0.04),
        2,
    )
    floor_tile_sqm = round(
        floor_area_sqm * num_floors * rng.uniform(0.72, 0.92),
        2,
    )
    wall_plaster_sqm = round(
        floor_area_sqm * num_floors * (2.35 + room_count * 0.08) * rng.normal(1.0, 0.05),
        2,
    )
    paint_sqm = round(wall_plaster_sqm * rng.uniform(0.82, 1.03), 2)
    electrical_points = int(round((room_count * 5.5 + bathroom_count * 2.5 + num_floors * 5) * rng.normal(1.0, 0.08)))
    total_plumbing_fixtures = int(round((bathroom_count * 4.0 + num_floors * 1.5) * rng.normal(1.0, 0.07)))

    structural_complexity_score = round(
        clamp(
            1.0
            + (num_floors - 1) * 0.45
            + (floor_area_sqm / 400.0) * 0.45
            + (room_count / 8.0) * 0.25
            + rng.normal(0, 0.05),
            1.0,
            2.8,
        ),
        3,
    )

    total_labour_days = int(
        round(
            (
                floor_area_sqm * num_floors * 1.65
                + total_concrete_m3 * 1.4
                + total_brickwork_m3 * 1.9
                + floor_tile_sqm * 0.18
                + paint_sqm * 0.10
                + electrical_points * 0.9
                + total_plumbing_fixtures * 1.3
            )
            * rng.normal(1.0, 0.05)
        )
    )

    # Phase durations: each duration is strongly connected to its relevant
    # quantities, with small random variation for realism.
    foundation_days = positive_int(
        4.5
        + foundation_excavation_m3 * 0.12
        + foundation_concrete_m3 * 0.28
        + num_floors * 2.0
        + rng.normal(0, 1.2),
        5,
    )
    structure_days = positive_int(
        8.0
        + total_concrete_m3 * 0.20
        + steel_kg_estimate / 420.0
        + num_floors * 5.5
        + structural_complexity_score * 3.0
        + rng.normal(0, 1.8),
        10,
    )
    masonry_days = positive_int(
        5.0 + total_brickwork_m3 * 0.38 + room_count * 0.8 + rng.normal(0, 1.2),
        5,
    )
    roofing_days = positive_int(
        3.5 + roof_area_sqm * 0.055 + num_floors * 0.8 + rng.normal(0, 0.9),
        4,
    )
    electrical_days = positive_int(
        3.0 + electrical_points * 0.18 + num_floors * 1.3 + rng.normal(0, 0.9),
        4,
    )
    plumbing_days = positive_int(
        3.0 + total_plumbing_fixtures * 0.55 + bathroom_count * 1.2 + rng.normal(0, 0.9),
        4,
    )
    plastering_days = positive_int(
        4.0 + wall_plaster_sqm * 0.035 + num_floors * 1.0 + rng.normal(0, 1.1),
        5,
    )
    finishing_days = positive_int(
        5.0
        + floor_tile_sqm * 0.035
        + room_count * 1.2
        + finish_grade * 2.3
        + rng.normal(0, 1.3),
        7,
    )
    painting_days = positive_int(
        3.0 + paint_sqm * 0.024 + finish_grade * 0.8 + rng.normal(0, 0.9),
        4,
    )
    external_work_days = positive_int(
        3.0 + floor_area_sqm * 0.022 + num_floors * 0.8 + rng.normal(0, 1.0),
        4,
    )
    handover_days = positive_int(
        2.0 + room_count * 0.25 + finish_grade * 0.45 + rng.normal(0, 0.45),
        2,
    )

    # Construction schedule logic with overlap:
    # foundation -> structure -> masonry/roofing
    # electrical and plumbing can overlap with plastering after masonry starts.
    # finishing waits for plastering and MEP rough-ins. Painting overlaps partly
    # with finishing. External works can overlap the last part of finishing.
    foundation_end = foundation_days
    structure_end = foundation_end + structure_days
    masonry_end = structure_end + masonry_days
    roofing_end = structure_end + roofing_days

    mep_start_offset = structure_end + int(round(masonry_days * 0.35))
    electrical_end = mep_start_offset + electrical_days
    plumbing_end = mep_start_offset + plumbing_days

    plastering_start = structure_end + int(round(masonry_days * 0.55))
    plastering_end = plastering_start + plastering_days

    finishing_start = max(plastering_end, electrical_end, plumbing_end, roofing_end)
    finishing_end = finishing_start + finishing_days

    painting_start = finishing_start + int(round(finishing_days * 0.35))
    painting_end = painting_start + painting_days

    external_start = max(structure_end, finishing_end - int(round(external_work_days * 0.45)))
    external_end = external_start + external_work_days

    handover_start = max(finishing_end, painting_end, external_end)
    handover_end = handover_start + handover_days

    total_duration_days = int(handover_end)

    return {
        "project_id": f"RP{index:04d}",
        "num_floors": num_floors,
        "floor_area_sqm": floor_area_sqm,
        "built_up_area_sqft": built_up_area_sqft,
        "room_count": room_count,
        "bathroom_count": bathroom_count,
        "foundation_excavation_m3": foundation_excavation_m3,
        "foundation_concrete_m3": foundation_concrete_m3,
        "total_concrete_m3": total_concrete_m3,
        "steel_kg_estimate": steel_kg_estimate,
        "total_brickwork_m3": total_brickwork_m3,
        "roof_area_sqm": roof_area_sqm,
        "floor_tile_sqm": floor_tile_sqm,
        "wall_plaster_sqm": wall_plaster_sqm,
        "paint_sqm": paint_sqm,
        "electrical_points": max(1, electrical_points),
        "total_plumbing_fixtures": max(1, total_plumbing_fixtures),
        "total_labour_days": max(1, total_labour_days),
        "structural_complexity_score": structural_complexity_score,
        "foundation_days": foundation_days,
        "structure_days": structure_days,
        "masonry_days": masonry_days,
        "roofing_days": roofing_days,
        "electrical_days": electrical_days,
        "plumbing_days": plumbing_days,
        "plastering_days": plastering_days,
        "finishing_days": finishing_days,
        "painting_days": painting_days,
        "external_work_days": external_work_days,
        "handover_days": handover_days,
        "total_duration_days": total_duration_days,
    }


def generate_dataset(n_records: int = N_RECORDS) -> pd.DataFrame:
    """Generate the full synthetic dataset."""

    rng = np.random.default_rng(SEED)
    records = [generate_record(i, rng) for i in range(1, n_records + 1)]
    return pd.DataFrame(records)


def main() -> None:
    """Generate and save the residential timeline dataset."""

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    df = generate_dataset()
    df.to_csv(OUTPUT_PATH, index=False)

    duration_cols = [
        "foundation_days",
        "structure_days",
        "masonry_days",
        "roofing_days",
        "electrical_days",
        "plumbing_days",
        "plastering_days",
        "finishing_days",
        "painting_days",
        "external_work_days",
        "handover_days",
        "total_duration_days",
    ]

    print("Synthetic residential construction dataset generated successfully.")
    print(f"Records: {len(df)}")
    print(f"Output : {OUTPUT_PATH}")
    print("\nDuration summary:")
    print(df[duration_cols].describe().loc[["mean", "min", "max"]].round(2))


if __name__ == "__main__":
    main()
