"""
Grafana JSON datasource feed.

Queries TimescaleDB for time-series progress metrics and formats the
results in the Grafana SimpleJSON / JSON API plugin format so Grafana
panels can poll this service directly.

Supported metrics
-----------------
actual_completion_pct
planned_completion_pct
schedule_performance_index
schedule_variance
labour_count
material_deliveries
weather_delay_days
rework_incidents
rolling_7day_progress_rate
"""

import logging
import os
from datetime import datetime, timezone
from typing import Any

import asyncpg

logger = logging.getLogger(__name__)

# Metric → TimescaleDB column name
METRIC_COLUMN_MAP: dict[str, str] = {
    "actual_completion_pct": "actual_completion_pct",
    "planned_completion_pct": "planned_completion_pct",
    "schedule_performance_index": "schedule_performance_index",
    "schedule_variance": "schedule_variance",
    "labour_count": "labour_count",
    "material_deliveries": "material_deliveries",
    "weather_delay_days": "weather_delay_days",
    "rework_incidents": "rework_incidents",
    "rolling_7day_progress_rate": "rolling_7day_progress_rate",
}

PROGRESS_TABLE = os.getenv("TIMESCALE_PROGRESS_TABLE", "construction_progress")


class GrafanaDashboardFeed:
    """
    Bridges TimescaleDB and Grafana's JSON datasource API.

    Usage::

        feed = GrafanaDashboardFeed()
        data = await feed.get_timeseries("proj-001", "schedule_performance_index",
                                         from_dt, to_dt)
    """

    def __init__(self) -> None:
        self._dsn = self._build_dsn()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_timeseries(
        self,
        project_id: str,
        metric: str,
        from_date: datetime,
        to_date: datetime,
    ) -> list[dict[str, Any]]:
        """
        Query TimescaleDB and return time-series data in Grafana format.

        Parameters
        ----------
        project_id : str
        metric : str
            One of the keys in ``METRIC_COLUMN_MAP``.
        from_date : datetime
            Start of the query window (timezone-aware UTC).
        to_date : datetime
            End of the query window (timezone-aware UTC).

        Returns
        -------
        list[dict]
            Each item: ``{"timestamp": <unix_ms>, "value": <float>}``.
            Compatible with Grafana's JSON datasource ``/query`` endpoint.

        Raises
        ------
        ValueError
            If *metric* is not a recognised metric name.
        """
        if metric not in METRIC_COLUMN_MAP:
            raise ValueError(
                f"Unknown metric '{metric}'. Valid metrics: {list(METRIC_COLUMN_MAP)}"
            )

        column = METRIC_COLUMN_MAP[metric]
        from_date = self._ensure_utc(from_date)
        to_date = self._ensure_utc(to_date)

        try:
            conn = await asyncpg.connect(self._dsn)
            rows = await self._query(conn, project_id, column, from_date, to_date)
            await conn.close()
        except asyncpg.PostgresError as exc:
            logger.exception("TimescaleDB query failed for project %s / metric %s: %s", project_id, metric, exc)
            # Return empty series rather than propagating — Grafana handles gaps gracefully.
            return []

        return [
            {
                "timestamp": int(row["ts"].timestamp() * 1000),   # Unix ms for Grafana
                "value": float(row["value"]) if row["value"] is not None else None,
            }
            for row in rows
        ]

    async def get_all_metrics(
        self,
        project_id: str,
        from_date: datetime,
        to_date: datetime,
    ) -> dict[str, list[dict[str, Any]]]:
        """
        Fetch all supported metrics in one call.

        Returns
        -------
        dict
            ``{metric_name: [{"timestamp": ms, "value": float}, ...]}``.
        """
        result: dict[str, list] = {}
        conn = await asyncpg.connect(self._dsn)
        try:
            for metric, column in METRIC_COLUMN_MAP.items():
                try:
                    rows = await self._query(conn, project_id, column, from_date, to_date)
                    result[metric] = [
                        {
                            "timestamp": int(row["ts"].timestamp() * 1000),
                            "value": float(row["value"]) if row["value"] is not None else None,
                        }
                        for row in rows
                    ]
                except Exception as exc:  # pylint: disable=broad-except
                    logger.warning("Failed to fetch metric '%s': %s", metric, exc)
                    result[metric] = []
        finally:
            await conn.close()

        return result

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    async def _query(
        conn: asyncpg.Connection,
        project_id: str,
        column: str,
        from_date: datetime,
        to_date: datetime,
    ) -> list[asyncpg.Record]:
        """
        Execute a parameterised TimescaleDB query.

        TODO: add time_bucket() aggregation for large time ranges.
        """
        sql = f"""
            SELECT
                recorded_at  AS ts,
                {column}     AS value
            FROM {PROGRESS_TABLE}
            WHERE project_id = $1
              AND recorded_at >= $2
              AND recorded_at <= $3
            ORDER BY recorded_at ASC
        """
        return await conn.fetch(sql, project_id, from_date, to_date)

    @staticmethod
    def _build_dsn() -> str:
        """Construct the asyncpg DSN from environment variables."""
        host = os.getenv("TIMESCALE_HOST", "localhost")
        port = os.getenv("TIMESCALE_PORT", "5432")
        db = os.getenv("TIMESCALE_DB", "construction")
        user = os.getenv("TIMESCALE_USER", "postgres")
        password = os.getenv("TIMESCALE_PASSWORD", "")
        return f"postgresql://{user}:{password}@{host}:{port}/{db}"

    @staticmethod
    def _ensure_utc(dt: datetime) -> datetime:
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt
