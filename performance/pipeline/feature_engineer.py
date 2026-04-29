"""
Feature engineering for the delay prediction pipeline.

Combines progress time-series features, site attributes from the Building
Schema (Component 01), and financial attributes from the Cost Report
(Component 02) into a single model-ready DataFrame.

Feature groups
--------------
Progress    schedule_variance, SPI, CPI proxy, rolling_7day_progress_rate,
            days_since_phase_start
Site        floors, footprint_sqm, structural_complexity_score
Financial   total_labour_days, phase_budget_consumed_pct
Environmental cumulative_weather_delay_days, rework_rate_per_100_labour_days
"""

import logging
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

ROLLING_WINDOW = 7          # days for rolling progress rate
MIN_PERIODS = 1             # allow partial windows at the start of a project


class FeatureEngineer:
    """
    Builds the feature matrix consumed by ``DelayPredictor``.

    Usage::

        fe = FeatureEngineer()
        X = fe.build_features(progress_df, building_schema, cost_report)
    """

    def build_features(
        self,
        progress_df: pd.DataFrame,
        building_schema: dict[str, Any],
        cost_report: dict[str, Any],
    ) -> pd.DataFrame:
        """
        Construct the full feature matrix from all three data sources.

        Parameters
        ----------
        progress_df : pd.DataFrame
            Cleaned DataFrame produced by ``Preprocessor.fit_transform``.
        building_schema : dict
            Building Schema JSON from Component 01.
        cost_report : dict
            Cost Report JSON from Component 02.

        Returns
        -------
        pd.DataFrame
            One row per progress record enriched with all feature groups.
        """
        if progress_df.empty:
            logger.warning("build_features called with empty DataFrame")
            return pd.DataFrame()

        df = progress_df.copy()

        df = self._add_progress_features(df)
        df = self._add_site_features(df, building_schema)
        df = self._add_financial_features(df, cost_report)
        df = self._add_environmental_features(df)

        logger.info("Feature matrix built: %d rows × %d columns", len(df), len(df.columns))
        return df

    # ------------------------------------------------------------------
    # Feature groups
    # ------------------------------------------------------------------

    def _add_progress_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Schedule and productivity features derived from the progress time-series."""
        # schedule_variance and schedule_performance_index already present from normaliser
        df["spi"] = df.get("schedule_performance_index", pd.Series(1.0, index=df.index))

        # CPI proxy: use budget data if available, else fall back to SPI
        # TODO: wire in real earned-value CPI once Component 02 streams costs.
        df["cpi_proxy"] = df.get("cpi", df["spi"])

        # Rolling 7-day progress rate (pct points per day)
        if "timestamp" in df.columns and "actual_completion_pct" in df.columns:
            df = df.sort_values("timestamp").reset_index(drop=True)
            df["rolling_7day_progress_rate"] = (
                df["actual_completion_pct"]
                .diff()
                .rolling(ROLLING_WINDOW, min_periods=MIN_PERIODS)
                .mean()
                .fillna(0.0)
            )
        else:
            df["rolling_7day_progress_rate"] = 0.0

        # Days since phase start
        if "timestamp" in df.columns and "phase" in df.columns:
            df["days_since_phase_start"] = (
                df.groupby("phase")["timestamp"]
                .transform(lambda s: (s - s.min()).dt.days)
                .fillna(0)
                .astype(int)
            )
        else:
            df["days_since_phase_start"] = 0

        return df

    @staticmethod
    def _add_site_features(df: pd.DataFrame, building_schema: dict[str, Any]) -> pd.DataFrame:
        """Scalar site attributes broadcast to every row."""
        # TODO: map Building Schema field names once Component 01 schema is finalised.
        df["floors"] = building_schema.get("floors", building_schema.get("num_floors", 0))
        df["footprint_sqm"] = building_schema.get(
            "footprint_sqm", building_schema.get("gross_floor_area_sqm", 0.0)
        )
        df["structural_complexity_score"] = building_schema.get(
            "structural_complexity_score", 1.0
        )
        return df

    @staticmethod
    def _add_financial_features(df: pd.DataFrame, cost_report: dict[str, Any]) -> pd.DataFrame:
        """Budget and labour features from the Cost Report (Component 02)."""
        # TODO: parse nested cost_report structure once Component 02 schema is finalised.
        df["total_labour_days"] = cost_report.get(
            "total_labour_days", cost_report.get("labour", {}).get("total_days", 0)
        )

        # Phase budget consumed %: look for phase-level breakdown first
        phase_budgets: dict = cost_report.get("phase_budgets", {})
        if phase_budgets and "phase" in df.columns:
            df["phase_budget_consumed_pct"] = df["phase"].map(
                lambda p: phase_budgets.get(p, {}).get("consumed_pct", 0.0)
            )
        else:
            df["phase_budget_consumed_pct"] = cost_report.get("overall_budget_consumed_pct", 0.0)

        return df

    @staticmethod
    def _add_environmental_features(df: pd.DataFrame) -> pd.DataFrame:
        """Cumulative weather delays and rework rate."""
        if "weather_delay_days" in df.columns:
            df["cumulative_weather_delay_days"] = df["weather_delay_days"].cumsum()
        else:
            df["cumulative_weather_delay_days"] = 0

        # Rework rate: incidents per 100 labour days
        if "rework_incidents" in df.columns and "labour_count" in df.columns:
            total_labour = df["labour_count"].replace(0, np.nan)
            df["rework_rate_per_100_labour_days"] = (
                df["rework_incidents"] / total_labour * 100
            ).fillna(0.0)
        else:
            df["rework_rate_per_100_labour_days"] = 0.0

        return df
