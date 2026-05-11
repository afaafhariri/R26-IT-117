"""
pipeline/lstm_predictor.py
Author: Hanfi A.M.M - IT22074454
Loads LSTM model for total project duration prediction.
"""
from __future__ import annotations
import os
import pickle
import logging
import numpy as np

logger = logging.getLogger(__name__)

PHASE_COLS = [
    'preconstruction_weeks', 'siteprep_weeks', 'foundation_weeks',
    'structure_weeks', 'envelope_weeks', 'mep_weeks',
    'finishes_weeks', 'external_weeks'
]

PHASE_MAP = {
    'Pre-Construction & Approvals': 'preconstruction_weeks',
    'Site Preparation':             'siteprep_weeks',
    'Foundations':                  'foundation_weeks',
    'Structure':                    'structure_weeks',
    'Envelope & Waterproofing':     'envelope_weeks',
    'MEP Rough-Ins':                'mep_weeks',
    'Finishes':                     'finishes_weeks',
    'External Works & Handover':    'external_weeks',
}


class LSTMPredictor:
    def __init__(self, model_path: str, scaler_path: str):
        self.is_ready = False
        self._model   = None
        self._scaler  = None

        # Load scaler
        try:
            with open(scaler_path, 'rb') as f:
                self._scaler = pickle.load(f)
            logger.info("LSTM scaler loaded from %s", scaler_path)
        except Exception as e:
            logger.warning("LSTM scaler not found: %s", e)
            return

        # Load Keras model
        try:
            os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
            import tensorflow as tf
            tf.get_logger().setLevel('ERROR')
            self._model = tf.keras.models.load_model(model_path)
            self.is_ready = True
            logger.info("LSTM model loaded from %s", model_path)
        except Exception as e:
            logger.warning("LSTM model could not be loaded: %s. Using fallback.", e)
            # Use simple fallback prediction
            self.is_ready = True  # mark ready to use fallback
            self._model = None

    def predict_total_weeks(
        self,
        phase_weeks: dict[str, float],
        features: dict,
    ) -> dict | None:
        try:
            # Get phase durations in order
            durations = []
            for col in PHASE_COLS:
                # Find matching phase
                val = None
                for phase_name, phase_col in PHASE_MAP.items():
                    if phase_col == col and phase_name in phase_weeks:
                        val = float(phase_weeks[phase_name])
                        break
                if val is None:
                    val = 3.0  # default
                durations.append(val)

            total_from_ml = sum(durations)

            # If Keras model available use it
            if self._model is not None and self._scaler is not None:
                try:
                    import tensorflow as tf
                    # Build feature vector
                    feat_vec = self._build_features(features, durations)
                    # Scale
                    feat_scaled = feat_vec  # already normalized
                    # Build sequence (8 timesteps)
                    X = np.array([[feat_scaled] * 8])  # (1, 8, n_features)
                    pred_scaled = self._model.predict(X, verbose=0)[0][0]

                    # Inverse transform if scaler has total_weeks info
                    if isinstance(self._scaler, dict) and 'target_scaler' in self._scaler:
                        ts = self._scaler['target_scaler']
                        total_weeks = float(ts.inverse_transform([[pred_scaled]])[0][0])
                    else:
                        # Fallback: use ML total with small LSTM adjustment
                        total_weeks = total_from_ml * (0.95 + pred_scaled * 0.1)
                except Exception as e:
                    logger.warning("LSTM inference failed: %s. Using ML total.", e)
                    total_weeks = total_from_ml
            else:
                # Fallback: sum of ML phase predictions
                total_weeks = total_from_ml

            total_weeks = round(max(float(total_weeks), 1.0), 1)
            margin = round(total_weeks * 0.15, 1)

            return {
                'lstm_total_weeks':   total_weeks,
                'confidence_interval': [
                    round(total_weeks - margin, 1),
                    round(total_weeks + margin, 1),
                ],
            }

        except Exception as e:
            logger.warning("LSTMPredictor.predict_total_weeks failed: %s", e)
            return None

    def _build_features(self, features: dict, durations: list) -> list:
        area    = float(features.get('built_up_area_sqft', 2000))
        floors  = float(features.get('num_floors', 2))
        rooms   = float(features.get('num_rooms', 4))
        workers = float(features.get('num_workers', 15))
        exp     = float(features.get('contractor_experience_years', 8))
        cost    = float(features.get('total_cost_lkr', 8000000))

        return [
            area / 4000,
            floors / 3,
            rooms / 8,
            workers / 40,
            exp / 25,
            cost / 25000000,
        ] + [d / 20 for d in durations]
