"""
Productivity analyser.

Aggregates normalised progress records into project-level and
phase-level productivity metrics, then projects the completion date
using Facebook Prophet.
"""

import logging
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

LABOUR_EFFICIENCY_DENOMINATOR = 8   # assumed productive hours per worker per day


class ProductivityAnalyser:
    """
    Computes productivity metrics from a list of normalised progress records.

    Usage::

        analyser = ProductivityAnalyser()
        metrics  = analyser.analyse(progress_records)
    """

    def analyse(self, progress_records: list[dict[str, Any]]) -> dict[str, Any]:
        """
        Aggregate productivity metrics across all progress records.

        Parameters
        ----------
        progress_records : list[dict]
            Normalised records from ``ProgressNormaliser.normalise``.

        Returns
        -------
        dict with keys:
            overall_spi              float
            phase_breakdown          list[dict]
            labour_efficiency_index  float
            projected_completion_date str (ISO date)
            days_ahead_or_behind     int  (negative = behind)
        """
        if not progress_records:
            logger.warning("analyse() called with empty record list")
            return self._empty_result()

        df = pd.DataFrame(progress_records)

        overall_spi = self._compute_overall_spi(df)
        phase_breakdown = self._phase_breakdown(df)
        lei = self._labour_efficiency_index(df)
        projected_date, days_delta = self._project_completion(df)

        return {
            "overall_spi": round(overall_spi, 4),
            "phase_breakdown": phase_breakdown,
            "labour_efficiency_index": round(lei, 4),
            "projected_completion_date": projected_date.isoformat(),
            "days_ahead_or_behind": days_delta,
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_overall_spi(df: pd.DataFrame) -> float:
        """Mean SPI across all records (weighted by planned_completion_pct)."""
        if "schedule_performance_index" not in df.columns:
            return 1.0
        weights = df.get("planned_completion_pct", pd.Series(1.0, index=df.index))
        weights = weights.replace(0, np.nan).fillna(1.0)
        spi_vals = df["schedule_performance_index"].fillna(1.0)
        return float(np.average(spi_vals, weights=weights))

    @staticmethod
    def _phase_breakdown(df: pd.DataFrame) -> list[dict[str, Any]]:
        """Per-phase SPI, completion %, and total rework incidents."""
        if "phase" not in df.columns:
            return []

        breakdown = []
        for phase, group in df.groupby("phase"):
            avg_spi = float(group["schedule_performance_index"].mean()) if "schedule_performance_index" in group else 1.0
            latest_actual = float(group["actual_completion_pct"].max()) if "actual_completion_pct" in group else 0.0
            total_rework = int(group["rework_incidents"].sum()) if "rework_incidents" in group else 0

            breakdown.append({
                "phase": phase,
                "average_spi": round(avg_spi, 4),
                "latest_completion_pct": round(latest_actual, 2),
                "total_rework_incidents": total_rework,
                "is_delayed": avg_spi < 0.90,
            })

        breakdown.sort(key=lambda x: x["phase"])
        return breakdown

    @staticmethod
    def _labour_efficiency_index(df: pd.DataFrame) -> float:
        """
        Labour Efficiency Index = actual progress per labour-day.

        LEI = mean(actual_completion_pct) / (sum(labour_count) * hours_per_day)

        Normalised to [0, 1] — values > 1 indicate exceptional productivity.
        """
        if "labour_count" not in df.columns or "actual_completion_pct" not in df.columns:
            return 1.0

        total_labour_days = float(df["labour_count"].sum())
        if total_labour_days == 0:
            return 0.0

        mean_progress = float(df["actual_completion_pct"].mean())
        lei = (mean_progress / 100.0) / (total_labour_days / max(len(df), 1))
        return min(lei, 10.0)   # cap at 10x for display sanity

    def _project_completion(
        self, df: pd.DataFrame
    ) -> tuple[date, int]:
        """
        Use Prophet to forecast when actual_completion_pct will reach 100 %.

        Falls back to a linear extrapolation when Prophet cannot fit
        (e.g. fewer than 2 data points).

        Returns
        -------
        (projected_date, days_ahead_or_behind)
            days_ahead_or_behind is positive when ahead of schedule.
        """
        try:
            return self._prophet_forecast(df)
        except Exception as exc:
            logger.warning("Prophet forecast failed (%s) — falling back to linear", exc)
            return self._linear_forecast(df)

    @staticmethod
    def _prophet_forecast(df: pd.DataFrame) -> tuple[date, int]:
        """Fit Prophet on actual_completion_pct time-series and forecast to 100%."""
        from prophet import Prophet  # noqa: PLC0415

        if "timestamp" not in df.columns or "actual_completion_pct" not in df.columns:
            raise ValueError("Missing timestamp or actual_completion_pct")

        prophet_df = df[["timestamp", "actual_completion_pct"]].dropna().copy()
        prophet_df = prophet_df.rename(
            columns={"timestamp": "ds", "actual_completion_pct": "y"}
        )
        prophet_df["ds"] = pd.to_datetime(prophet_df["ds"], utc=True).dt.tz_localize(None)

        if len(prophet_df) < 2:
            raise ValueError("Insufficient data for Prophet (need ≥ 2 points)")

        model = Prophet(yearly_seasonality=False, weekly_seasonality=True, daily_seasonality=False)
        model.fit(prophet_df, iter=300)  # fewer iterations for low-latency inference

        # Forecast up to 365 future days looking for the 100% crossing
        future = model.make_future_dataframe(periods=365, freq="D")
        forecast = model.predict(future)

        crossing = forecast[forecast["yhat"] >= 100.0]
        if crossing.empty:
            projected = forecast["ds"].iloc[-1].date()
        else:
            projected = crossing["ds"].iloc[0].date()

        # Compare to the last planned_completion_pct date if available
        today = date.today()
        days_delta = (today - projected).days   # positive = ahead

        return projected, days_delta

    @staticmethod
    def _linear_forecast(df: pd.DataFrame) -> tuple[date, int]:
        """Simple linear extrapolation when Prophet is unavailable."""
        if "actual_completion_pct" not in df.columns or len(df) < 2:
            return date.today() + timedelta(days=180), -180

        latest_pct = float(df["actual_completion_pct"].iloc[-1])
        first_pct = float(df["actual_completion_pct"].iloc[0])
        n_days = max(len(df) - 1, 1)
        daily_rate = (latest_pct - first_pct) / n_days

        if daily_rate <= 0:
            projected = date.today() + timedelta(days=365)
            return projected, -365

        remaining_pct = 100.0 - latest_pct
        days_remaining = int(remaining_pct / daily_rate)
        projected = date.today() + timedelta(days=days_remaining)
        return projected, 0

    @staticmethod
    def _empty_result() -> dict[str, Any]:
        return {
            "overall_spi": 1.0,
            "phase_breakdown": [],
            "labour_efficiency_index": 0.0,
            "projected_completion_date": (date.today() + timedelta(days=365)).isoformat(),
            "days_ahead_or_behind": 0,
        }
