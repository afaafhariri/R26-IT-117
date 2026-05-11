"""
data/generate_dataset.py
Generate 500 synthetic Sri Lankan construction project records.

Run from the timeline/ directory:
    python data/generate_dataset.py
Output: data/construction_projects.csv
"""

import os
import numpy as np
import pandas as pd

# ── Reproducibility ────────────────────────────────────────────────────────────
np.random.seed(42)
N    = 500
NOISE = 0.05   # low noise multiplier so correlations are strong

# ── Categorical pools ──────────────────────────────────────────────────────────
DISTRICTS = [
    'Colombo', 'Gampaha', 'Kalutara', 'Kandy', 'Matale', 'Nuwara Eliya',
    'Galle', 'Matara', 'Hambantota', 'Jaffna', 'Kilinochchi', 'Mannar',
    'Vavuniya', 'Batticaloa', 'Ampara', 'Trincomalee', 'Kurunegala',
    'Puttalam', 'Anuradhapura', 'Polonnaruwa', 'Badulla', 'Monaragala',
    'Ratnapura', 'Kegalle', 'Mullaitivu',
]
CONSTRUCTION_TYPES = ['Residential', 'Commercial', 'Industrial', 'Mixed-Use']
SOIL_TYPES         = ['Clay', 'Sandy', 'Loam', 'Rocky', 'Laterite', 'Alluvial']

# ── Helper: clamp + round to 1 dp ──────────────────────────────────────────────
def clamp(arr, lo, hi):
    return np.clip(np.round(arr, 1), lo, hi)

def noise(n, scale=1.0):
    """Zero-mean Gaussian noise scaled by NOISE constant."""
    return np.random.normal(0, NOISE * scale, n)

# ── Base project attributes ────────────────────────────────────────────────────
project_id         = [f'PRJ-{i+1:04d}' for i in range(N)]
district           = np.random.choice(DISTRICTS, N)
construction_type  = np.random.choice(CONSTRUCTION_TYPES, N,
                                      p=[0.55, 0.25, 0.12, 0.08])
soil_type          = np.random.choice(SOIL_TYPES, N,
                                      p=[0.20, 0.18, 0.22, 0.15, 0.15, 0.10])

# ── Continuous inputs ──────────────────────────────────────────────────────────
built_up_area_sqft = np.random.randint(800,  15_001, N).astype(float)
num_floors         = np.random.randint(1,     6,     N).astype(float)
num_rooms          = (num_floors * np.random.uniform(2, 5, N)).astype(int).astype(float)
num_bathrooms      = np.clip(
    (num_rooms * np.random.uniform(0.3, 0.6, N)).astype(int), 1, None
).astype(float)

# Budget proportional to area + floors; commercial/industrial costs more
type_cost_mult = np.where(
    construction_type == 'Industrial', 1.4,
    np.where(construction_type == 'Commercial', 1.25,
    np.where(construction_type == 'Mixed-Use',  1.15, 1.0))
)
total_cost_lkr   = np.round(built_up_area_sqft * num_floors * np.random.uniform(4_500, 9_000, N) * type_cost_mult, -3)
material_cost_lkr = np.round(total_cost_lkr * np.random.uniform(0.50, 0.65, N), -3)

num_workers                 = np.random.randint(5, 61, N).astype(float)
contractor_experience_years = np.random.randint(1, 31, N).astype(float)
start_month                 = np.random.randint(1, 13, N).astype(float)

# Labour hours: area × floors × random hours/sqft
labor_hours_total = np.round(
    built_up_area_sqft * num_floors * np.random.uniform(0.8, 2.2, N)
).astype(float)

# Delay flag: higher probability for large/complex projects and rocky soil
delay_prob = 0.15 + 0.10 * (num_floors >= 4) + 0.08 * (soil_type == 'Rocky')
had_delays = (np.random.rand(N) < delay_prob).astype(int)

# ── Derived normalised signals (all in [0, 1]) ──────────────────────────────────
# Used to build correlated phase durations without leaking raw values.

area_n   = (built_up_area_sqft - 800)  / (15_000 - 800)     # 0=small, 1=large
floors_n = (num_floors - 1) / 4                               # 0=1F, 1=5F
rooms_n  = (num_rooms  - 2) / 23                             # normalised
bath_n   = (num_bathrooms - 1) / 9

# Soil difficulty: Rocky=worst, Sandy=moderate, rest=easy
soil_diff = np.where(soil_type == 'Rocky',  1.0,
            np.where(soil_type == 'Clay',   0.7,
            np.where(soil_type == 'Sandy',  0.5,
            np.where(soil_type == 'Laterite', 0.4,
            np.where(soil_type == 'Alluvial', 0.3, 0.2)))))   # Loam

# Complexity: commercial/industrial more complex
complexity = np.where(
    construction_type == 'Industrial', 1.0,
    np.where(construction_type == 'Commercial', 0.75,
    np.where(construction_type == 'Mixed-Use',  0.55, 0.30))
)

# Experience inversely reduces duration (max 30 yrs → 0 penalty)
exp_factor = 1.0 - contractor_experience_years / 40.0   # [0.25, 0.975]

# Delay multiplier
delay_mult = 1.0 + had_delays * np.random.uniform(0.05, 0.20, N)

# Monsoon penalty: May–Oct = months 5–10 add friction
monsoon = np.isin(start_month, [5, 6, 7, 8, 9, 10]).astype(float)

# ── Phase durations ────────────────────────────────────────────────────────────
# Each formula is a weighted mix of the most relevant signals, then scaled into
# the phase's (min, max) window and jittered with low Gaussian noise.

def make_duration(base_signal, lo, hi, extra_noise_scale=1.0):
    """Map base_signal ∈ [0,1] → [lo, hi] with low noise."""
    raw = lo + base_signal * (hi - lo)
    raw = raw + noise(N, extra_noise_scale)
    return clamp(raw, lo, hi)

# 1. Pre-Construction & Approvals  (2–8 wks)
#    Driven by: complexity, num_floors, district (authority speed ~ random), exp
pre_signal = (0.35 * complexity + 0.30 * floors_n + 0.20 * exp_factor
              + 0.15 * monsoon)
preconstruction_weeks = make_duration(pre_signal, 2, 8)

# 2. Site Preparation  (1–4 wks)
#    Driven by: area, soil difficulty
site_signal = 0.55 * area_n + 0.45 * soil_diff
siteprep_weeks = make_duration(site_signal, 1, 4)

# 3. Foundations  (2–8 wks)
#    Driven by: area, floors, soil difficulty
found_signal = (0.30 * area_n + 0.35 * floors_n + 0.35 * soil_diff)
foundation_weeks = make_duration(found_signal * delay_mult, 2, 8)

# 4. Structure  (4–16 wks)
#    Driven by: area, floors, rooms (largest phase — strong signal)
struct_signal = (0.40 * area_n + 0.40 * floors_n + 0.20 * rooms_n)
structure_weeks = make_duration(struct_signal * delay_mult, 4, 16, extra_noise_scale=2.0)

# 5. Envelope & Waterproofing  (2–8 wks)
#    Driven by: area, floors
env_signal = 0.55 * area_n + 0.45 * floors_n
envelope_weeks = make_duration(env_signal * delay_mult, 2, 8)

# 6. MEP Rough-Ins  (2–6 wks)
#    Driven by: rooms, bathrooms, floors
mep_signal = (0.35 * rooms_n + 0.40 * bath_n + 0.25 * floors_n)
mep_weeks = make_duration(mep_signal, 2, 6)

# 7. Finishes  (3–10 wks)
#    Driven by: rooms, area, floors; quality increases with cost/sqft
cost_per_sqft_n = np.clip(
    (total_cost_lkr / built_up_area_sqft - 4_500) / (9_000 - 4_500), 0, 1
)
fin_signal = (0.30 * rooms_n + 0.30 * area_n + 0.20 * floors_n
              + 0.20 * cost_per_sqft_n)
finishes_weeks = make_duration(fin_signal * delay_mult, 3, 10, extra_noise_scale=1.5)

# 8. External Works & Handover  (1–4 wks)
#    Driven by: area
ext_signal = 0.80 * area_n + 0.20 * complexity
external_weeks = make_duration(ext_signal, 1, 4)

# ── Total ──────────────────────────────────────────────────────────────────────
total_weeks = np.round(
    preconstruction_weeks + siteprep_weeks + foundation_weeks +
    structure_weeks + envelope_weeks + mep_weeks +
    finishes_weeks + external_weeks, 1
)

# ── Assemble DataFrame ─────────────────────────────────────────────────────────
df = pd.DataFrame({
    'project_id':                  project_id,
    'district':                    district,
    'construction_type':           construction_type,
    'soil_type':                   soil_type,
    'built_up_area_sqft':          built_up_area_sqft,
    'num_floors':                  num_floors,
    'num_rooms':                   num_rooms,
    'num_bathrooms':               num_bathrooms,
    'total_cost_lkr':              total_cost_lkr,
    'labor_hours_total':           labor_hours_total,
    'material_cost_lkr':           material_cost_lkr,
    'contractor_experience_years': contractor_experience_years,
    'start_month':                 start_month,
    'num_workers':                 num_workers,
    'had_delays':                  had_delays,
    # ── Phase targets ────────────────────────────────────────────────
    'preconstruction_weeks':       preconstruction_weeks,
    'siteprep_weeks':              siteprep_weeks,
    'foundation_weeks':            foundation_weeks,
    'structure_weeks':             structure_weeks,
    'envelope_weeks':              envelope_weeks,
    'mep_weeks':                   mep_weeks,
    'finishes_weeks':              finishes_weeks,
    'external_weeks':              external_weeks,
    'total_weeks':                 total_weeks,
})

# ── Save ───────────────────────────────────────────────────────────────────────
out_dir  = os.path.dirname(os.path.abspath(__file__))
out_path = os.path.join(out_dir, 'construction_projects.csv')
df.to_csv(out_path, index=False)
print(f"Saved {len(df)} records → {out_path}\n")

# ── Summary table ──────────────────────────────────────────────────────────────
phase_cols = [
    'preconstruction_weeks', 'siteprep_weeks', 'foundation_weeks',
    'structure_weeks', 'envelope_weeks', 'mep_weeks',
    'finishes_weeks', 'external_weeks', 'total_weeks',
]

summary = df[phase_cols].agg(['mean', 'min', 'max', 'std']).T.round(2)
summary.columns = ['Mean', 'Min', 'Max', 'StdDev']
summary.index.name = 'Phase Column'

print("─" * 62)
print(f"{'Phase Column':<32} {'Mean':>6} {'Min':>5} {'Max':>5} {'StdDev':>8}")
print("─" * 62)
for col, row in summary.iterrows():
    print(f"{col:<32} {row['Mean']:>6.2f} {row['Min']:>5.1f} {row['Max']:>5.1f} {row['StdDev']:>8.2f}")
print("─" * 62)

# ── Quick correlation check ────────────────────────────────────────────────────
print("\nCorrelation of key inputs with structure_weeks (should be > 0.6):")
for col in ['built_up_area_sqft', 'num_floors', 'num_rooms']:
    r = df[col].corr(df['structure_weeks'])
    print(f"  {col:<30}: r = {r:.3f}")

print("\nCorrelation of soil_diff proxy with foundation_weeks (should be > 0.4):")
df['_soil_diff'] = np.where(df['soil_type']=='Rocky', 1.0,
                   np.where(df['soil_type']=='Clay',   0.7,
                   np.where(df['soil_type']=='Sandy',  0.5, 0.3)))
print(f"  soil difficulty score       : r = {df['_soil_diff'].corr(df['foundation_weeks']):.3f}")
df.drop(columns=['_soil_diff'], inplace=True)
