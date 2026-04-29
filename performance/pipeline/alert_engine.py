"""
Alert evaluation and publishing engine.

Evaluates five alert conditions against each incoming prediction and
progress record, builds structured alert payloads, and publishes them
to a Redis pub/sub channel named ``alerts.{project_id}``.

Alert types and thresholds
--------------------------
DELAY_WARNING       delay_risk == "high"
SCHEDULE_SLIP       SPI < 0.85 for 3 consecutive updates
PRODUCTIVITY_DROP   rolling_progress_rate < 0.5 % per day
MATERIAL_RISK       material_deliveries == 0 for 5+ consecutive days
REWORK_SPIKE        rework_rate > 5 per 100 labour days
"""

import json
import logging
import uuid
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# Thresholds
DELAY_RISK_TRIGGER = "high"
SCHEDULE_SLIP_SPI = 0.85
SCHEDULE_SLIP_CONSECUTIVE = 3
PRODUCTIVITY_DROP_RATE = 0.5          # % per day
MATERIAL_RISK_ZERO_DAYS = 5
REWORK_SPIKE_RATE = 5.0               # incidents per 100 labour days

# Redis key ttl for the alert list (7 days)
ALERT_LIST_TTL_SECONDS = 7 * 24 * 3600


class AlertEngine:
    """
    Stateful alert evaluator.

    Maintains per-project sliding windows to detect conditions that
    require consecutive threshold breaches (SCHEDULE_SLIP, MATERIAL_RISK).

    Parameters
    ----------
    redis_client : redis.asyncio.Redis | None
        Async Redis client. If None, publishing is skipped (useful in tests).
    """

    def __init__(self, redis_client=None) -> None:
        self._redis = redis_client
        # project_id → deque of recent SPI values
        self._spi_history: dict[str, deque] = defaultdict(lambda: deque(maxlen=SCHEDULE_SLIP_CONSECUTIVE))
        # project_id → consecutive days with zero material deliveries
        self._zero_delivery_streak: dict[str, int] = defaultdict(int)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate(
        self,
        delay_prediction: dict[str, Any],
        progress_record: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """
        Evaluate all alert conditions and return a list of triggered alerts.

        Parameters
        ----------
        delay_prediction : dict
            Output of ``DelayPredictor.predict``.
        progress_record : dict
            Normalised progress record from ``ProgressNormaliser.normalise``.

        Returns
        -------
        list[dict]
            Zero or more alert payloads, each conforming to the alert schema.
        """
        alerts: list[dict] = []
        project_id: str = progress_record.get("project_id", "unknown")

        # Update sliding-window state before evaluating conditions
        self._update_state(project_id, progress_record)

        # --- Evaluate each rule ---
        alert = self._check_delay_warning(project_id, delay_prediction, progress_record)
        if alert:
            alerts.append(alert)

        alert = self._check_schedule_slip(project_id, progress_record)
        if alert:
            alerts.append(alert)

        alert = self._check_productivity_drop(project_id, progress_record)
        if alert:
            alerts.append(alert)

        alert = self._check_material_risk(project_id, progress_record)
        if alert:
            alerts.append(alert)

        alert = self._check_rework_spike(project_id, progress_record)
        if alert:
            alerts.append(alert)

        if alerts:
            logger.info("Generated %d alert(s) for project %s", len(alerts), project_id)

        return alerts

    async def publish_alert(self, alert: dict[str, Any]) -> None:
        """
        Push an alert to the Redis pub/sub channel and cache it in a list.

        Channel name: ``alerts.{project_id}``
        The list is capped at 50 entries via LTRIM and expires after 7 days.

        Parameters
        ----------
        alert : dict
            An alert payload produced by ``evaluate``.
        """
        if self._redis is None:
            logger.debug("Redis unavailable — alert not published: %s", alert.get("type"))
            return

        project_id = alert.get("project_id", "unknown")
        channel = f"alerts.{project_id}"
        list_key = f"alert_list.{project_id}"

        payload = json.dumps(alert, default=str)

        try:
            await self._redis.publish(channel, payload)
            await self._redis.lpush(list_key, payload)
            await self._redis.ltrim(list_key, 0, 49)   # keep latest 50
            await self._redis.expire(list_key, ALERT_LIST_TTL_SECONDS)
            logger.debug("Alert published to channel '%s': %s", channel, alert.get("type"))
        except Exception as exc:
            logger.exception("Failed to publish alert to Redis: %s", exc)

    # ------------------------------------------------------------------
    # Alert rule evaluators
    # ------------------------------------------------------------------

    def _check_delay_warning(
        self,
        project_id: str,
        prediction: dict[str, Any],
        record: dict[str, Any],
    ) -> dict | None:
        if prediction.get("delay_risk") != DELAY_RISK_TRIGGER:
            return None

        days = prediction.get("predicted_delay_days", 0)
        cause = prediction.get("primary_cause", "unspecified")

        return self._build_alert(
            project_id=project_id,
            alert_type="DELAY_WARNING",
            severity="critical",
            message=(
                f"High delay risk detected. Predicted {days} day(s) behind schedule. "
                f"Primary driver: {cause}."
            ),
            recommended_action=(
                "Convene an immediate site review. Identify resource bottlenecks "
                "and update the schedule baseline with the project manager."
            ),
        )

    def _check_schedule_slip(
        self, project_id: str, record: dict[str, Any]
    ) -> dict | None:
        history = self._spi_history[project_id]
        if len(history) < SCHEDULE_SLIP_CONSECUTIVE:
            return None
        if all(spi < SCHEDULE_SLIP_SPI for spi in history):
            worst_spi = round(min(history), 3)
            return self._build_alert(
                project_id=project_id,
                alert_type="SCHEDULE_SLIP",
                severity="warning",
                message=(
                    f"SPI has been below {SCHEDULE_SLIP_SPI} for "
                    f"{SCHEDULE_SLIP_CONSECUTIVE} consecutive updates. "
                    f"Current worst SPI: {worst_spi}."
                ),
                recommended_action=(
                    "Review crew allocation and material supply chain. "
                    "Consider fast-tracking critical-path activities."
                ),
            )
        return None

    def _check_productivity_drop(
        self, project_id: str, record: dict[str, Any]
    ) -> dict | None:
        rate = float(record.get("rolling_7day_progress_rate", record.get("actual_completion_pct", 0)))
        if rate >= PRODUCTIVITY_DROP_RATE:
            return None
        return self._build_alert(
            project_id=project_id,
            alert_type="PRODUCTIVITY_DROP",
            severity="warning",
            message=(
                f"Rolling 7-day progress rate is {rate:.2f}%/day, "
                f"below the threshold of {PRODUCTIVITY_DROP_RATE}%/day."
            ),
            recommended_action=(
                "Investigate labour efficiency. Check for unrecorded weather delays, "
                "absenteeism, or equipment downtime."
            ),
        )

    def _check_material_risk(
        self, project_id: str, record: dict[str, Any]
    ) -> dict | None:
        streak = self._zero_delivery_streak[project_id]
        if streak < MATERIAL_RISK_ZERO_DAYS:
            return None
        return self._build_alert(
            project_id=project_id,
            alert_type="MATERIAL_RISK",
            severity="critical",
            message=(
                f"Zero material deliveries recorded for {streak} consecutive day(s). "
                "Supply chain disruption likely."
            ),
            recommended_action=(
                "Contact suppliers immediately. Activate contingency procurement "
                "channels and assess impact on the critical path."
            ),
        )

    def _check_rework_spike(
        self, project_id: str, record: dict[str, Any]
    ) -> dict | None:
        rework_rate = float(record.get("rework_rate_per_100_labour_days", 0.0))
        if rework_rate <= REWORK_SPIKE_RATE:
            return None
        return self._build_alert(
            project_id=project_id,
            alert_type="REWORK_SPIKE",
            severity="warning",
            message=(
                f"Rework rate is {rework_rate:.1f} incidents per 100 labour days, "
                f"exceeding the threshold of {REWORK_SPIKE_RATE}."
            ),
            recommended_action=(
                "Review QA inspection logs. Increase on-site supervision "
                "and identify the root-cause phase or trade."
            ),
        )

    # ------------------------------------------------------------------
    # State management
    # ------------------------------------------------------------------

    def _update_state(self, project_id: str, record: dict[str, Any]) -> None:
        """Maintain sliding windows used by multi-period rules."""
        spi = float(record.get("schedule_performance_index", 1.0))
        self._spi_history[project_id].append(spi)

        deliveries = int(record.get("material_deliveries", 0))
        if deliveries == 0:
            self._zero_delivery_streak[project_id] += 1
        else:
            self._zero_delivery_streak[project_id] = 0

    # ------------------------------------------------------------------
    # Builder
    # ------------------------------------------------------------------

    @staticmethod
    def _build_alert(
        project_id: str,
        alert_type: str,
        severity: str,
        message: str,
        recommended_action: str,
    ) -> dict[str, Any]:
        return {
            "alert_id": str(uuid.uuid4()),
            "project_id": project_id,
            "type": alert_type,
            "severity": severity,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "recommended_action": recommended_action,
        }
