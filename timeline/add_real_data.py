"""
Add Real Sri Lankan Construction Project Data to Training Set
Author: Hanfi A.M.M - IT22074454
Run: python add_real_data.py
"""

import pandas as pd
import numpy as np
import os

# ── Real project data extracted from PDFs ─────────────────
# Source: M/S Athambawa and Sons, Sri Lanka (2024-2026)

real_data = [
    {
        # PDF 1: Two-storey Residence - Mr. Mahroof, Nintavur
        # Total: 190 days = 27 weeks
        # Masonry(27d) + Doors(80d) = Structural ~15.4w
        # Electrical(80d) + Plumbing(51d) + HVAC(35d) = MEP ~12w
        # Plastering(25d) + Waterproofing(15d) + Flooring(8d) + Painting = Finishing ~10w
        'project_id': 'REAL_MRB_001',
        'district': 'Ampara',
        'construction_type': 'Two-storey',
        'soil_type': 'Medium',
        'built_up_area_sqft': 2800,
        'num_floors': 2,
        'num_rooms': 5,
        'num_bathrooms': 3,
        'total_cost_lkr': 18000000,
        'labor_hours_total': 3200,
        'material_cost_lkr': 11000000,
        'contractor_experience_years': 15,
        'start_month': 4,
        'num_workers': 20,
        'had_delays': 1,
        'foundation_weeks': 0,   # post-structural - no foundation phase
        'structural_weeks': 15,  # masonry + blockwork + frames
        'roofing_weeks': 0,      # post-structural - no roofing
        'mep_weeks': 12,         # electrical + plumbing + HVAC
        'finishing_weeks': 10,   # plastering + waterproofing + flooring + painting
        'total_weeks': 27,
    },
    {
        # PDF 2: Single-storey Post Office - Kaluwanchi/Jayanthipura
        # Total: 126 days = 18 weeks
        # Foundation: excavation(18d) + concrete(105d overlap) = ~4w
        # Structural: superstructure(93d) = ~13w
        # Roofing: roofing(14d) = 2w
        # MEP: electrical(21d) + plumbing(14d) = ~5w
        # Finishing: walls+floors+finishes(25d) + painting(8d) = ~5w
        'project_id': 'REAL_PO_001',
        'district': 'Ampara',
        'construction_type': 'Single-storey',
        'soil_type': 'Medium',
        'built_up_area_sqft': 1200,
        'num_floors': 1,
        'num_rooms': 4,
        'num_bathrooms': 2,
        'total_cost_lkr': 8500000,
        'labor_hours_total': 1800,
        'material_cost_lkr': 5200000,
        'contractor_experience_years': 10,
        'start_month': 10,
        'num_workers': 12,
        'had_delays': 0,
        'foundation_weeks': 4,
        'structural_weeks': 13,
        'roofing_weeks': 2,
        'mep_weeks': 5,
        'finishing_weeks': 5,
        'total_weeks': 29,
    },
    {
        # PDF 3: Three-storey District Secretariat - Ampara Stage VI
        # Total: 210 days = 30 weeks (balance works)
        # Foundation: gravelling+brickwork+concreting = ~4w
        # Structural: floor levels work(33d x3) = ~14w
        # Roofing: not applicable (balance works)
        # MEP: plumbing(145d)+electrical(145d) concurrent = ~21w
        # Finishing: plastering(12d)+painting(150d) = ~4w
        'project_id': 'REAL_DS_001',
        'district': 'Ampara',
        'construction_type': 'Three-storey',
        'soil_type': 'Hard',
        'built_up_area_sqft': 4500,
        'num_floors': 3,
        'num_rooms': 12,
        'num_bathrooms': 6,
        'total_cost_lkr': 45000000,
        'labor_hours_total': 8000,
        'material_cost_lkr': 28000000,
        'contractor_experience_years': 20,
        'start_month': 3,
        'num_workers': 35,
        'had_delays': 0,
        'foundation_weeks': 4,
        'structural_weeks': 14,
        'roofing_weeks': 2,
        'mep_weeks': 21,
        'finishing_weeks': 4,
        'total_weeks': 45,
    },
    {
        # PDF 4: Police Station Renovation - Nuwaraeliya
        # Total: 364 days = 52 weeks
        # Foundation: excavation+soakage pit(75d) = ~11w
        # Structural: floor level works(33d x4) = ~19w
        # Roofing: not main phase
        # MEP: electrical(145d)+plumbing(145d) = ~21w
        # Finishing: painting(150d) = ~21w
        'project_id': 'REAL_PS_001',
        'district': 'Nuwaraeliya',
        'construction_type': 'Three-storey',
        'soil_type': 'Soft',
        'built_up_area_sqft': 6000,
        'num_floors': 3,
        'num_rooms': 15,
        'num_bathrooms': 8,
        'total_cost_lkr': 65000000,
        'labor_hours_total': 12000,
        'material_cost_lkr': 40000000,
        'contractor_experience_years': 18,
        'start_month': 10,
        'num_workers': 40,
        'had_delays': 1,
        'foundation_weeks': 11,
        'structural_weeks': 19,
        'roofing_weeks': 2,
        'mep_weeks': 21,
        'finishing_weeks': 21,
        'total_weeks': 74,
    },
    {
        # PDF 5: Veterinary Offices - Trincomalee
        # Total: 91 days = 13 weeks
        # Foundation: excavation(5d)+filling(10d)+lean(1d) = ~2w
        # Structural: formwork(36d)+concreting(20d)+brickwork(14d) = ~4w
        # Roofing: not listed separately
        # MEP: plumbing(17d)+electrical(27d) = ~6w
        # Finishing: finishes(38d)+painting(7d) = ~6w
        'project_id': 'REAL_VET_001',
        'district': 'Trincomalee',
        'construction_type': 'Single-storey',
        'soil_type': 'Medium',
        'built_up_area_sqft': 1800,
        'num_floors': 1,
        'num_rooms': 6,
        'num_bathrooms': 3,
        'total_cost_lkr': 12000000,
        'labor_hours_total': 2200,
        'material_cost_lkr': 7500000,
        'contractor_experience_years': 12,
        'start_month': 9,
        'num_workers': 15,
        'had_delays': 0,
        'foundation_weeks': 2,
        'structural_weeks': 4,
        'roofing_weeks': 1,
        'mep_weeks': 6,
        'finishing_weeks': 6,
        'total_weeks': 19,
    },
    {
        # PDF 6: Samurdhi Office - Monaragala
        # Total: 60 days = ~9 weeks
        # Foundation: excavation(2d)+concrete(9d) = ~2w
        # Structural: concreting+brickwork(9d) = ~1w
        # Roofing: roofing(5d) = 1w
        # MEP: plumbing+electrical(9d) = ~1w
        # Finishing: waterproofing(7d)+painting(16d) = ~3w
        'project_id': 'REAL_SAM_001',
        'district': 'Monaragala',
        'construction_type': 'Single-storey',
        'soil_type': 'Medium',
        'built_up_area_sqft': 900,
        'num_floors': 1,
        'num_rooms': 3,
        'num_bathrooms': 2,
        'total_cost_lkr': 5500000,
        'labor_hours_total': 1200,
        'material_cost_lkr': 3400000,
        'contractor_experience_years': 8,
        'start_month': 10,
        'num_workers': 10,
        'had_delays': 0,
        'foundation_weeks': 2,
        'structural_weeks': 1,
        'roofing_weeks': 1,
        'mep_weeks': 1,
        'finishing_weeks': 3,
        'total_weeks': 8,
    },
]

# ── Load synthetic dataset ────────────────────────────────
print("="*55)
print("  Adding Real Data to Training Set")
print("  Hanfi A.M.M - IT22074454")
print("="*55)

df_synthetic = pd.read_csv('data/construction_projects.csv')
print(f"\n  Synthetic records : {len(df_synthetic)}")

# ── Create real data DataFrame ────────────────────────────
df_real = pd.DataFrame(real_data)
print(f"  Real records      : {len(df_real)}")

# ── Combine ───────────────────────────────────────────────
df_combined = pd.concat([df_synthetic, df_real], ignore_index=True)
print(f"  Combined total    : {len(df_combined)}")

# ── Save combined dataset ─────────────────────────────────
os.makedirs('data', exist_ok=True)
df_combined.to_csv('data/construction_projects.csv', index=False)

print(f"\n  Real projects added:")
for _, row in df_real.iterrows():
    print(f"  - {row['project_id']}: {row['construction_type']} | {row['district']} | {row['total_weeks']}w total")

print(f"\n  Saved to: data/construction_projects.csv")
print(f"\n  Now run: python train.py")
print("="*55)
