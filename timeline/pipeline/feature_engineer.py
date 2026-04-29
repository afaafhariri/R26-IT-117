import math
import pandas as pd

class FeatureEngineer:
    """
    Creates derived features from the preprocessed data to improve XGBoost performance.
    """

    def build_features(self, preprocessed_df: pd.DataFrame) -> pd.DataFrame:
        """
        Derives analytical features (Scale, Complexity, Labour, Financial, Location).
        
        Args:
            preprocessed_df: single-row DataFrame from Preprocessor.
        
        Returns:
            pd.DataFrame: New DataFrame containing feature-engineered columns.
        """
        try:
            df = preprocessed_df.copy()

            # Scale features
            df["perimeter_m"] = df["footprint_sqm"].apply(lambda x: 4 * math.sqrt(x) if x > 0 else 0)

            # Complexity features (using stubs)
            df["roof_complexity"] = df.get("roof_type_encoded", 0)  # simple=0, complex=1
            df["has_basement"] = df.get("has_basement", 0)  # TODO: extract this in preprocessor instead

            # Labour features
            df["labour_days_per_sqm"] = df["total_labour_days"] / df["total_area_sqm"]
            df["labour_days_per_sqm"] = df["labour_days_per_sqm"].fillna(0).replace([float('inf'), -float('inf')], 0)

            # Financial features
            # TODO: Add real financial features (cost_per_sqm, material_to_labour_ratio)
            df["cost_per_sqm"] = 0.0
            df["material_to_labour_ratio"] = 1.0

            # Location features
            # df["district_encoded"] = df.get("district_encoded", 0)

            return df
        
        except Exception as e:
            raise ValueError(f"Error during feature engineering: {str(e)}")
