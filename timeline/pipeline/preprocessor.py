"""
pipeline/preprocessor.py
Author: Hanfi A.M.M - IT22074454
"""
import os
import pickle
import pandas as pd
import numpy as np

KNOWN_DISTRICTS = [
    'Colombo','Gampaha','Kalutara','Kandy','Galle',
    'Matara','Kurunegala','Ratnapura','Ampara','Badulla',
    'Batticaloa','Hambantota','Jaffna','Kegalle','Kilinochchi',
    'Mannar','Matale','Monaragala','Mullaitivu','Nuwara Eliya',
    'Polonnaruwa','Puttalam','Trincomalee','Vavuniya'
]
KNOWN_CTYPES = ['Single-storey','Two-storey','Three-storey']
KNOWN_SOILS  = ['Hard','Medium','Soft']

MODEL_DIR = os.path.join(os.path.dirname(__file__), '..', 'models')


class Preprocessor:
    def __init__(self):
        self._encoders = None
        self._load_encoders()

    def _load_encoders(self):
        path = os.path.join(MODEL_DIR, 'encoders.pkl')
        if os.path.exists(path):
            with open(path, 'rb') as f:
                self._encoders = pickle.load(f)

    def prepare(self, payload: dict) -> pd.DataFrame:
        df = pd.DataFrame([payload])

        # Fill optional fields
        area = float(df['built_up_area_sqft'].iloc[0])
        cost = float(df['total_cost_lkr'].iloc[0])

        if 'labor_hours_total' not in df.columns or pd.isna(df['labor_hours_total'].iloc[0]):
            df['labor_hours_total'] = area * 0.9
        if 'material_cost_lkr' not in df.columns or pd.isna(df['material_cost_lkr'].iloc[0]):
            df['material_cost_lkr'] = cost * 0.62

        # Encode district
        district = df['district'].iloc[0] if 'district' in df.columns else 'Colombo'
        if self._encoders and 'district' in self._encoders:
            try:
                df['district_enc'] = self._encoders['district'].transform([district])[0]
            except Exception:
                df['district_enc'] = 0
        else:
            d = str(district).strip()
            df['district_enc'] = KNOWN_DISTRICTS.index(d) if d in KNOWN_DISTRICTS else 0

        # Encode construction type
        ctype = df['construction_type'].iloc[0] if 'construction_type' in df.columns else 'Single-storey'
        if self._encoders and 'type' in self._encoders:
            try:
                df['type_enc'] = self._encoders['type'].transform([ctype])[0]
            except Exception:
                df['type_enc'] = 0
        else:
            c = str(ctype).strip()
            df['type_enc'] = KNOWN_CTYPES.index(c) if c in KNOWN_CTYPES else 0

        # Encode soil type
        soil = df['soil_type'].iloc[0] if 'soil_type' in df.columns else 'Medium'
        if self._encoders and 'soil' in self._encoders:
            try:
                df['soil_enc'] = self._encoders['soil'].transform([soil])[0]
            except Exception:
                df['soil_enc'] = 1
        else:
            s = str(soil).strip().capitalize()
            df['soil_enc'] = KNOWN_SOILS.index(s) if s in KNOWN_SOILS else 1

        # Extract start_month from start_date
        if 'start_date' in df.columns:
            df['start_month'] = pd.to_datetime(df['start_date']).dt.month
        elif '_start_month' in df.columns:
            df['start_month'] = df['_start_month']
        else:
            df['start_month'] = 6

        return df
