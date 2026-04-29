import xgboost as xgb
import pandas as pd
from typing import Dict
from timeline.pipeline import phases

class ScheduleModel:
    """
    Predicts the duration of each construction phase using trained XGBoost models.
    """
    
    def __init__(self):
        # Dictionary of pre-trained models per phase
        self.models: Dict[str, xgb.XGBRegressor] = {}

    def predict_phase_durations(self, features: pd.DataFrame) -> dict[str, int]:
        """
        Returns working days dictionary for all 18 phases.
        
        Args:
            features: 1-row DataFrame output from FeatureEngineer.
            
        Returns:
            dict[str, int]: Map of phase name to its predicted working days.
        """
        try:
            row = features.iloc[0]
            footprint = row.get("footprint_sqm", 0)
            total_area = row.get("total_area_sqm", 0)

            # TODO: replace stubs with self.models[phase].predict(features)
            durations = {
                phases.SITE_PREPARATION: max(3, int(footprint * 0.05)),
                phases.FOUNDATION: max(7, int(footprint * 0.15)),
                phases.SUPERSTRUCTURE: max(14, int(total_area * 0.25)),
                phases.BRICKWORK_AND_BLOCKWORK: max(10, int(total_area * 0.10)),
                phases.ROOF_STRUCTURE: max(5, int(footprint * 0.10)),
                phases.ROOF_COVERING: max(3, int(footprint * 0.05)),
                phases.EXTERNAL_PLASTERING: max(7, int(total_area * 0.08)),
                phases.INTERNAL_PLASTERING: max(10, int(total_area * 0.12)),
                phases.FLOOR_FINISHING: max(7, int(total_area * 0.10)),
                phases.DOOR_AND_WINDOW_FIXING: max(5, int(total_area * 0.05)),
                phases.ELECTRICAL_FIRST_FIX: max(5, int(total_area * 0.05)),
                phases.PLUMBING_FIRST_FIX: max(5, int(total_area * 0.05)),
                phases.CEILING: max(5, int(footprint * 0.08)),
                phases.PAINTING: max(7, int(total_area * 0.15)),
                phases.ELECTRICAL_SECOND_FIX: max(3, int(total_area * 0.04)),
                phases.PLUMBING_SECOND_FIX: max(3, int(total_area * 0.04)),
                phases.EXTERNAL_WORKS: max(5, int(footprint * 0.10)),
                phases.FINAL_INSPECTION: 2,
            }

            # Ensure strict int
            return {k: max(1, int(v)) for k, v in durations.items()}

        except Exception as e:
            raise ValueError(f"Error predicting phase durations: {str(e)}")

    def train(self, X: pd.DataFrame, y_phases: pd.DataFrame) -> None:
        """
        Trains one XGBoost model per phase.
        
        Args:
            X: Dataframe containing training features.
            y_phases: Dataframe where each column is the working days duration of a phase.
        """
        # TODO: Implement full training loop and grid search here
        pass
