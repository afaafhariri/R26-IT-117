"""
Progress record normaliser.

Transforms raw Kafka / manual-entry progress messages into a clean,
enriched dictionary ready for the preprocessing pipeline.

Derived metrics
---------------
schedule_variance          actual_pct - planned_pct
schedule_performance_index actual_pct / planned_pct  (clamped to [0, 2])
is_delayed                 True when SPI < 0.90
days_behind                estimated calendar days behind schedule
"""

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

SPI_DELAY_THRESHOLD = 0.90
SPI_CLAMP_MAX = 2.0
ESTIMATED_TOTAL_DAYS = 365  # fallback when no baseline is available


class ProgressNormaliser:
    """
    Stateless transformer applied to every incoming progress record.

    Usage::

        normaliser = ProgressNormaliser()
        clean = normaliser.normalise(raw_message)
    """

    def normalise(self, raw_message: dict[str, Any]) -> dict[str, Any]:
        """
        Validate and enrich a raw progress record.

        Parameters
        ----------
        raw_message : dict
            Message payload conforming to the Kafka schema.

        Returns
        -------
        dict
            Enriched record containing all original fields plus
            ``schedule_variance``, ``schedule_performance_index``,
            ``is_delayed``, and ``days_behind``.

        Raises
        ------
        ValueError
            If required fields are missing or contain invalid values.
        """
        self._validate(raw_message)

        planned_pct: float = float(raw_message["planned_completion_pct"])
        actual_pct: float = float(raw_message["actual_completion_pct"])

        schedule_variance = round(actual_pct - planned_pct, 4)
        spi = self._compute_spi(actual_pct, planned_pct)
        is_delayed = spi < SPI_DELAY_THRESHOLD
        days_behind = self._estimate_days_behind(schedule_variance)

        timestamp = raw_message.get("timestamp")
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp)
        if isinstance(timestamp, datetime) and timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)

        normalised: dict[str, Any] = {
            # --- original fields (sanitised) ---
            "project_id": str(raw_message["project_id"]).strip(),
            "timestamp": timestamp,
            "phase": str(raw_message.get("phase", "unknown")).strip().lower(),
            "planned_completion_pct": planned_pct,
            "actual_completion_pct": actual_pct,
            "labour_count": int(raw_message.get("labour_count", 0)),
            "material_deliveries": int(raw_message.get("material_deliveries", 0)),
            "weather_delay_days": int(raw_message.get("weather_delay_days", 0)),
            "rework_incidents": int(raw_message.get("rework_incidents", 0)),
            # --- derived metrics ---
            "schedule_variance": schedule_variance,
            "schedule_performance_index": spi,
            "is_delayed": is_delayed,
            "days_behind": days_behind,
        }

        logger.debug(
            "Normalised record — project=%s  SPI=%.3f  delayed=%s  days_behind=%d",
            normalised["project_id"],
            spi,
            is_delayed,
            days_behind,
        )
        return normalised

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate(record: dict[str, Any]) -> None:
        """Raise ValueError if required fields are absent or invalid."""
        required = {"project_id", "planned_completion_pct", "actual_completion_pct"}
        missing = required - record.keys()
        if missing:
            raise ValueError(f"Progress record missing required fields: {missing}")

        for pct_field in ("planned_completion_pct", "actual_completion_pct"):
            val = record[pct_field]
            try:
                val = float(val)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Field '{pct_field}' must be numeric, got: {val!r}") from exc
            if not (0.0 <= val <= 100.0):
                raise ValueError(f"Field '{pct_field}' must be in [0, 100], got: {val}")

    @staticmethod
    def _compute_spi(actual_pct: float, planned_pct: float) -> float:
        """
        SPI = actual / planned.

        Returns 1.0 (on schedule) when planned is 0 to avoid division by zero
        at the very start of a project.
        """
        if planned_pct == 0.0:
            return 1.0
        raw = actual_pct / planned_pct
        return round(min(raw, SPI_CLAMP_MAX), 4)

    @staticmethod
    def _estimate_days_behind(schedule_variance: float) -> int:
        """
        Approximate calendar days behind schedule from the percentage variance.

        Uses a simple linear mapping: each 1 % point of variance corresponds
        to ESTIMATED_TOTAL_DAYS / 100 days.

        TODO: replace with a project-specific calculation once the baseline
              schedule (from Building Schema / Component 01) is wired in.
        """
        if schedule_variance >= 0:
            return 0
        days_per_pct = ESTIMATED_TOTAL_DAYS / 100.0
        return int(abs(schedule_variance) * days_per_pct)
