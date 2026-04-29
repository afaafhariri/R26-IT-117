"""
Preprocessing pipeline for construction progress records.

Responsibilities
----------------
- Impute missing values
- Clip statistical outliers
- Encode categorical phase names (ordinal + one-hot)
- Scale numerical features with StandardScaler

The fitted scaler and encoder are stored on the instance so the same
transformation can be reapplied to incoming streaming records.
"""

import logging
from typing import Any

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler, OrdinalEncoder
from sklearn.impute import SimpleImputer

logger = logging.getLogger(__name__)

# Numerical columns subject to scaling and outlier clipping
NUMERICAL_COLS = [
    "planned_completion_pct",
    "actual_completion_pct",
    "labour_count",
    "material_deliveries",
    "weather_delay_days",
    "rework_incidents",
    "schedule_variance",
    "schedule_performance_index",
    "days_behind",
]

# Categorical columns to encode
CATEGORICAL_COLS = ["phase"]

# IQR multiplier for outlier clipping
IQR_FACTOR = 3.0


class Preprocessor:
    """
    Fit-transform pipeline for raw progress records.

    Usage::

        preprocessor = Preprocessor()
        df_clean = preprocessor.fit_transform(records)          # train
        df_new   = preprocessor.transform(new_records)          # inference
    """

    def __init__(self) -> None:
        self._scaler = StandardScaler()
        self._imputer = SimpleImputer(strategy="median")
        self._encoder = OrdinalEncoder(
            handle_unknown="use_encoded_value",
            unknown_value=-1,
        )
        self._fitted = False
        self._phase_categories: list[str] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fit_transform(self, progress_records: list[dict[str, Any]]) -> pd.DataFrame:
        """
        Fit the preprocessor on *progress_records* and return the
        cleaned, encoded, and scaled DataFrame.

        Parameters
        ----------
        progress_records : list[dict]
            Raw or normalised progress records (from ProgressNormaliser).

        Returns
        -------
        pd.DataFrame
            Processed DataFrame ready for feature engineering.
        """
        if not progress_records:
            logger.warning("fit_transform called with empty records list")
            return pd.DataFrame()

        df = pd.DataFrame(progress_records)
        df = self._coerce_types(df)
        df = self._impute(df, fit=True)
        df = self._clip_outliers(df)
        df = self._encode_categoricals(df, fit=True)
        df = self._scale_numerics(df, fit=True)

        self._fitted = True
        logger.info("Preprocessor fitted on %d records", len(df))
        return df

    def transform(self, progress_records: list[dict[str, Any]]) -> pd.DataFrame:
        """
        Apply a previously fitted preprocessor to new records.

        Raises
        ------
        RuntimeError
            If called before ``fit_transform``.
        """
        if not self._fitted:
            raise RuntimeError("Preprocessor must be fitted before calling transform(). "
                               "Call fit_transform() first.")

        df = pd.DataFrame(progress_records)
        df = self._coerce_types(df)
        df = self._impute(df, fit=False)
        df = self._clip_outliers(df)
        df = self._encode_categoricals(df, fit=False)
        df = self._scale_numerics(df, fit=False)
        return df

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _coerce_types(df: pd.DataFrame) -> pd.DataFrame:
        """Cast columns to expected dtypes; fill missing numerics with NaN."""
        for col in NUMERICAL_COLS:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
            else:
                df[col] = np.nan

        for col in CATEGORICAL_COLS:
            if col in df.columns:
                df[col] = df[col].astype(str).str.strip().str.lower()
            else:
                df[col] = "unknown"

        # Ensure timestamp is present and timezone-aware
        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")

        return df

    def _impute(self, df: pd.DataFrame, *, fit: bool) -> pd.DataFrame:
        """Median imputation for numerical columns."""
        num_cols_present = [c for c in NUMERICAL_COLS if c in df.columns]
        if not num_cols_present:
            return df

        if fit:
            df[num_cols_present] = self._imputer.fit_transform(df[num_cols_present])
        else:
            df[num_cols_present] = self._imputer.transform(df[num_cols_present])

        return df

    @staticmethod
    def _clip_outliers(df: pd.DataFrame) -> pd.DataFrame:
        """Clip values beyond IQR_FACTOR × IQR from the median."""
        for col in NUMERICAL_COLS:
            if col not in df.columns:
                continue
            q1 = df[col].quantile(0.25)
            q3 = df[col].quantile(0.75)
            iqr = q3 - q1
            lower = q1 - IQR_FACTOR * iqr
            upper = q3 + IQR_FACTOR * iqr
            df[col] = df[col].clip(lower=lower, upper=upper)
        return df

    def _encode_categoricals(self, df: pd.DataFrame, *, fit: bool) -> pd.DataFrame:
        """Ordinal-encode the phase column."""
        cat_cols_present = [c for c in CATEGORICAL_COLS if c in df.columns]
        if not cat_cols_present:
            return df

        if fit:
            df[[f"{c}_encoded" for c in cat_cols_present]] = self._encoder.fit_transform(
                df[cat_cols_present]
            )
            self._phase_categories = list(
                self._encoder.categories_[0] if self._encoder.categories_ else []
            )
        else:
            df[[f"{c}_encoded" for c in cat_cols_present]] = self._encoder.transform(
                df[cat_cols_present]
            )

        return df

    def _scale_numerics(self, df: pd.DataFrame, *, fit: bool) -> pd.DataFrame:
        """StandardScaler applied to numerical columns in-place."""
        num_cols_present = [c for c in NUMERICAL_COLS if c in df.columns]
        if not num_cols_present:
            return df

        scaled_col_names = [f"{c}_scaled" for c in num_cols_present]
        if fit:
            df[scaled_col_names] = self._scaler.fit_transform(df[num_cols_present])
        else:
            df[scaled_col_names] = self._scaler.transform(df[num_cols_present])

        return df
