"""
models/__init__.py - model loader for Component 04 (8 phases)
Author: Hanfi A.M.M - IT22074454 - SLIIT
"""

from __future__ import annotations
import logging, os, pickle
from typing import Any
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# 8 phase -> pkl filename map
_PHASE_FILES: dict[str, str] = {
    "Pre-Construction & Approvals": "preconstruction_weeks_model.pkl",
    "Site Preparation":             "siteprep_weeks_model.pkl",
    "Foundations":                  "foundation_weeks_model.pkl",
    "Structure":                    "structure_weeks_model.pkl",
    "Envelope & Waterproofing":     "envelope_weeks_model.pkl",
    "MEP Rough-Ins":                "mep_weeks_model.pkl",
    "Finishes":                     "finishes_weeks_model.pkl",
    "External Works & Handover":    "external_weeks_model.pkl",
}

_PHASE_RANGES: dict[str, tuple[float, float]] = {
    "Pre-Construction & Approvals": (2.0,  8.0),
    "Site Preparation":             (1.0,  4.0),
    "Foundations":                  (2.0,  8.0),
    "Structure":                    (4.0, 16.0),
    "Envelope & Waterproofing":     (2.0,  8.0),
    "MEP Rough-Ins":                (2.0,  6.0),
    "Finishes":                     (3.0, 10.0),
    "External Works & Handover":    (1.0,  4.0),
}

_PROPORTIONS: dict[str, float] = {
    "Pre-Construction & Approvals": 0.10,
    "Site Preparation":             0.05,
    "Foundations":                  0.12,
    "Structure":                    0.28,
    "Envelope & Waterproofing":     0.12,
    "MEP Rough-Ins":                0.10,
    "Finishes":                     0.16,
    "External Works & Handover":    0.07,
}

def _load_pkl(path: str) -> Any:
    with open(path, "rb") as fh:
        return pickle.load(fh)

class ScheduleModel:
    def __init__(self, phase_models, scaler, encoders, feature_names):
        self._phase_models  = phase_models
        self._scaler        = scaler
        self._encoders      = encoders or {}
        self._feature_names = feature_names or []
        self._model         = bool(phase_models)

    def predict_phase_durations(self, features: pd.DataFrame) -> dict[str, float]:
        if self._phase_models:
            return self._predict_with_models(features)
        return self._stub_predict(features)

    def _predict_with_models(self, features: pd.DataFrame) -> dict[str, float]:
        X = self._build_X(features)
        result: dict[str, float] = {}
        for phase, model in self._phase_models.items():
            try:
                pred = float(model.predict(X)[0])
            except Exception as exc:
                logger.warning("predict failed for %s: %s", phase, exc)
                pred = self._stub_phase(phase, features)
            lo, hi = _PHASE_RANGES[phase]
            result[phase] = round(float(np.clip(pred, lo, hi)), 1)
        for phase in _PHASE_FILES:
            if phase not in result:
                lo, hi = _PHASE_RANGES[phase]
                result[phase] = round(float(np.clip(self._stub_phase(phase, features), lo, hi)), 1)
        return result

    def _build_X(self, features: pd.DataFrame) -> pd.DataFrame:
        if self._feature_names:
            X = pd.DataFrame(index=features.index)
            for col in self._feature_names:
                X[col] = features[col].values if col in features.columns else 0.0
            if self._scaler is not None:
                try:
                    scaled = self._scaler.transform(X)
                    return pd.DataFrame(scaled, columns=self._feature_names)
                except Exception as exc:
                    logger.warning("Scaler transform failed: %s", exc)
            return X
        num_cols = [c for c in features.columns
                    if not c.startswith("raw_") and not c.startswith("_")
                    and features[c].dtype in (float, int, "float64", "int64")]
        return features[num_cols]

    def _stub_phase(self, phase: str, features: pd.DataFrame) -> float:
        row    = features.iloc[0]
        area   = float(row.get("built_up_area_sqft", 1500))
        floors = float(row.get("num_floors", 1))
        total  = (area / 1000) * 20.0 * floors
        return total * _PROPORTIONS.get(phase, 0.10)

    def _stub_predict(self, features: pd.DataFrame) -> dict[str, float]:
        row        = features.iloc[0]
        area       = float(row.get("built_up_area_sqft", 1500))
        floors     = float(row.get("num_floors", 1))
        workers    = float(row.get("num_workers", 10))
        experience = float(row.get("contractor_experience_years", 5))
        base   = (area / 1000) * 20.0 * floors
        total  = base * max(0.75, 1 - experience * 0.01)
        result: dict[str, float] = {}
        for phase, prop in _PROPORTIONS.items():
            lo, hi = _PHASE_RANGES[phase]
            result[phase] = round(float(np.clip(total * prop, lo, hi)), 1)
        return result


def load_model(model_dir: str | None = None) -> ScheduleModel:
    resolved = model_dir or os.path.join(os.path.dirname(__file__))
    scaler, encoders, feature_names = None, None, None

    for fname, attr in [("scaler.pkl","scaler"),("encoders.pkl","encoders"),("features.pkl","features")]:
        path = os.path.join(resolved, fname)
        if os.path.isfile(path):
            try:
                val = _load_pkl(path)
                if attr == "scaler":   scaler = val
                elif attr == "encoders": encoders = val
                else: feature_names = val
                logger.info("Loaded %s from %s", attr, path)
            except Exception as exc:
                logger.warning("Could not load %s: %s", attr, exc)

    phase_models: dict[str, Any] = {}
    for phase, filename in _PHASE_FILES.items():
        path = os.path.join(resolved, filename)
        if os.path.isfile(path):
            try:
                phase_models[phase] = _load_pkl(path)
                logger.info("Loaded model for '%s' from %s", phase, path)
            except Exception as exc:
                logger.warning("Could not load model for '%s': %s", phase, exc)
        else:
            logger.warning("Model file not found for '%s': %s", phase, path)

    if not phase_models:
        logger.warning("No phase models loaded - stub heuristics will be used.")

    return ScheduleModel(phase_models, scaler, encoders, feature_names)

__all__ = ["load_model", "ScheduleModel"]
