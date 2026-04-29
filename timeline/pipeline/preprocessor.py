import pandas as pd

class Preprocessor:
    """
    Preprocesses JSON data from Building Schema and Cost Report
    into a structured pandas DataFrame.
    """

    def prepare(self, building_schema: dict, cost_report: dict) -> pd.DataFrame:
        """
        Extracts and encodes relevant features.
        
        Args:
            building_schema: JSON payload from Component 01.
            cost_report: JSON payload from Component 02.
        
        Returns:
            pd.DataFrame: A single-row DataFrame containing the extracted features.
        """
        try:
            # TODO: Extract values carefully handling edge cases
            floors = building_schema.get("floors", 1)
            footprint_sqm = building_schema.get("footprint_sqm", 0.0)
            total_area_sqm = building_schema.get("total_area_sqm", 0.0)
            finish_grade = building_schema.get("finish_grade", "standard")
            roof_type = building_schema.get("roof_type", "flat")
            foundation_type = building_schema.get("foundation_type", "strip")
            is_coastal = 1 if building_schema.get("location_coastal", False) else 0

            total_labour_days = cost_report.get("total_labour_days", 0)
            structural_complexity_score = cost_report.get("structural_complexity_score", 1.0)
            # trade_value_breakdown = cost_report.get("trade_value_breakdown", {})

            # Encode finish_grade (e.g. 0: basic, 1: standard, 2: premium)
            finish_grade_map = {"basic": 0, "standard": 1, "premium": 2}
            finish_grade_encoded = finish_grade_map.get(finish_grade.lower(), 1)

            # TODO: Map roof type properly
            roof_type_encoded = 1 if roof_type.lower() != "flat" else 0

            # TODO: Map foundation type properly
            foundation_type_encoded = 1 if foundation_type.lower() == "raft" else 0

            data = {
                "floors": floors,
                "footprint_sqm": footprint_sqm,
                "total_area_sqm": total_area_sqm,
                "total_labour_days": total_labour_days,
                "structural_complexity_score": structural_complexity_score,
                "finish_grade_encoded": finish_grade_encoded,
                "roof_type_encoded": roof_type_encoded,
                "foundation_type_encoded": foundation_type_encoded,
                "is_coastal": is_coastal
            }

            return pd.DataFrame([data])
        
        except Exception as e:
            # Basic error handling
            raise ValueError(f"Error during preprocessing: {str(e)}")
