"""
pipeline/feature_engineer.py
Author: Hanfi A.M.M - IT22074454
"""
import pandas as pd
import numpy as np


class FeatureEngineer:

    _REQUIRED = [
        'built_up_area_sqft', 'num_floors', 'num_rooms', 'num_bathrooms',
        'total_cost_lkr', 'labor_hours_total', 'material_cost_lkr',
        'contractor_experience_years', 'num_workers', 'start_month',
    ]

    def build_features(self, df: pd.DataFrame) -> pd.DataFrame:
        self._validate(df)
        df = df.copy()

        area    = df['built_up_area_sqft'].astype(float)
        floors  = df['num_floors'].astype(float)
        rooms   = df['num_rooms'].astype(float)
        baths   = df['num_bathrooms'].astype(float)
        cost    = df['total_cost_lkr'].astype(float)
        labour  = df['labor_hours_total'].astype(float)
        matcost = df['material_cost_lkr'].astype(float)
        exp     = df['contractor_experience_years'].astype(float)
        workers = df['num_workers'].astype(float)
        month   = df['start_month'].astype(float)

        df['area_per_floor']    = area / floors
        df['cost_per_sqft']     = cost / area
        df['labor_per_sqft']    = labour / area
        df['rooms_per_floor']   = rooms / floors
        df['complexity_score']  = (area / 1000) + (floors * 1.5) + (rooms * 0.3)
        df['resource_density']  = workers / df['complexity_score']
        df['experience_factor'] = exp / 25
        df['is_monsoon']        = month.isin([5, 6, 7, 8, 9, 10]).astype(int)
        df['bath_per_floor']    = baths / floors
        df['cost_ratio']        = matcost / cost
        df['worker_per_floor']  = workers / floors

        return df

    def _validate(self, df: pd.DataFrame) -> None:
        missing = [c for c in self._REQUIRED if c not in df.columns]
        if missing:
            raise ValueError(
                f"FeatureEngineer.build_features — required columns missing: {missing}"
            )
