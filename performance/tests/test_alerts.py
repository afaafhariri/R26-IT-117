"""
Unit tests for the AlertEngine.

Each test verifies that exactly the right alert fires at its configured
threshold and that below-threshold records produce no alert.

Run with::

    pytest tests/test_alerts.py -v
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pipeline.alert_engine import (
    AlertEngine,
    DELAY_RISK_TRIGGER,
    MATERIAL_RISK_ZERO_DAYS,
    REWORK_SPIKE_RATE,
    SCHEDULE_SLIP_CONSECUTIVE,
    SCHEDULE_SLIP_SPI,
    PRODUCTIVITY_DROP_RATE,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_record(
    project_id: str = "proj-test",
    spi: float = 1.0,
    material_deliveries: int = 5,
    rework_rate: float = 0.0,
    rolling_progress_rate: float = 1.0,
    rework_incidents: int = 0,
    labour_count: int = 20,
) -> dict:
    return {
        "project_id": project_id,
        "timestamp": datetime.now(timezone.utc),
        "phase": "structure",
        "planned_completion_pct": 50.0,
        "actual_completion_pct": 50.0 * spi,
        "schedule_performance_index": spi,
        "material_deliveries": material_deliveries,
        "rework_rate_per_100_labour_days": rework_rate,
        "rolling_7day_progress_rate": rolling_progress_rate,
        "rework_incidents": rework_incidents,
        "labour_count": labour_count,
        "weather_delay_days": 0,
        "schedule_variance": 0.0,
        "days_behind": 0,
        "is_delayed": spi < 0.90,
    }


def make_prediction(
    delay_risk: str = "low",
    predicted_delay_days: int = 0,
    confidence: float = 0.8,
    primary_cause: str = "spi",
) -> dict:
    return {
        "delay_risk": delay_risk,
        "predicted_delay_days": predicted_delay_days,
        "confidence": confidence,
        "primary_cause": primary_cause,
    }


def alert_of_type(alerts: list[dict], alert_type: str) -> dict | None:
    return next((a for a in alerts if a["type"] == alert_type), None)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def engine():
    """AlertEngine with Redis stubbed out."""
    return AlertEngine(redis_client=None)


# ---------------------------------------------------------------------------
# DELAY_WARNING tests
# ---------------------------------------------------------------------------

class TestDelayWarning:

    def test_fires_when_risk_is_high(self, engine):
        prediction = make_prediction(delay_risk="high", predicted_delay_days=12)
        record = make_record(spi=0.70)
        alerts = engine.evaluate(prediction, record)
        alert = alert_of_type(alerts, "DELAY_WARNING")

        assert alert is not None
        assert alert["severity"] == "critical"
        assert "12" in alert["message"]

    def test_does_not_fire_when_risk_is_medium(self, engine):
        prediction = make_prediction(delay_risk="medium")
        record = make_record()
        alerts = engine.evaluate(prediction, record)
        assert alert_of_type(alerts, "DELAY_WARNING") is None

    def test_does_not_fire_when_risk_is_low(self, engine):
        prediction = make_prediction(delay_risk="low")
        record = make_record()
        alerts = engine.evaluate(prediction, record)
        assert alert_of_type(alerts, "DELAY_WARNING") is None

    def test_alert_has_required_keys(self, engine):
        prediction = make_prediction(delay_risk="high")
        record = make_record(spi=0.60)
        alerts = engine.evaluate(prediction, record)
        alert = alert_of_type(alerts, "DELAY_WARNING")

        for key in ("alert_id", "project_id", "type", "severity", "message",
                    "timestamp", "recommended_action"):
            assert key in alert, f"Missing key: {key}"


# ---------------------------------------------------------------------------
# SCHEDULE_SLIP tests
# ---------------------------------------------------------------------------

class TestScheduleSlip:

    def test_fires_after_consecutive_low_spi(self):
        engine = AlertEngine(redis_client=None)
        prediction = make_prediction(delay_risk="low")

        # Push SCHEDULE_SLIP_CONSECUTIVE records with SPI below threshold
        low_spi = SCHEDULE_SLIP_SPI - 0.01
        alerts = []
        for _ in range(SCHEDULE_SLIP_CONSECUTIVE):
            alerts = engine.evaluate(prediction, make_record(spi=low_spi))

        assert alert_of_type(alerts, "SCHEDULE_SLIP") is not None

    def test_does_not_fire_before_consecutive_threshold(self):
        engine = AlertEngine(redis_client=None)
        prediction = make_prediction(delay_risk="low")
        low_spi = SCHEDULE_SLIP_SPI - 0.01

        alerts = []
        for _ in range(SCHEDULE_SLIP_CONSECUTIVE - 1):
            alerts = engine.evaluate(prediction, make_record(spi=low_spi))

        assert alert_of_type(alerts, "SCHEDULE_SLIP") is None

    def test_does_not_fire_when_spi_recovers(self):
        engine = AlertEngine(redis_client=None)
        prediction = make_prediction(delay_risk="low")
        low_spi = SCHEDULE_SLIP_SPI - 0.01

        for _ in range(SCHEDULE_SLIP_CONSECUTIVE - 1):
            engine.evaluate(prediction, make_record(spi=low_spi))

        # One healthy record breaks the streak
        engine.evaluate(prediction, make_record(spi=1.0))
        alerts = engine.evaluate(prediction, make_record(spi=low_spi))
        assert alert_of_type(alerts, "SCHEDULE_SLIP") is None

    def test_severity_is_warning(self):
        engine = AlertEngine(redis_client=None)
        prediction = make_prediction(delay_risk="low")
        low_spi = SCHEDULE_SLIP_SPI - 0.01

        alerts = []
        for _ in range(SCHEDULE_SLIP_CONSECUTIVE):
            alerts = engine.evaluate(prediction, make_record(spi=low_spi))

        alert = alert_of_type(alerts, "SCHEDULE_SLIP")
        assert alert is not None
        assert alert["severity"] == "warning"


# ---------------------------------------------------------------------------
# PRODUCTIVITY_DROP tests
# ---------------------------------------------------------------------------

class TestProductivityDrop:

    def test_fires_when_rate_below_threshold(self, engine):
        low_rate = PRODUCTIVITY_DROP_RATE - 0.1
        record = make_record(rolling_progress_rate=low_rate)
        alerts = engine.evaluate(make_prediction(), record)
        assert alert_of_type(alerts, "PRODUCTIVITY_DROP") is not None

    def test_does_not_fire_at_threshold(self, engine):
        record = make_record(rolling_progress_rate=PRODUCTIVITY_DROP_RATE)
        alerts = engine.evaluate(make_prediction(), record)
        assert alert_of_type(alerts, "PRODUCTIVITY_DROP") is None

    def test_does_not_fire_above_threshold(self, engine):
        record = make_record(rolling_progress_rate=PRODUCTIVITY_DROP_RATE + 1.0)
        alerts = engine.evaluate(make_prediction(), record)
        assert alert_of_type(alerts, "PRODUCTIVITY_DROP") is None


# ---------------------------------------------------------------------------
# MATERIAL_RISK tests
# ---------------------------------------------------------------------------

class TestMaterialRisk:

    def test_fires_after_consecutive_zero_deliveries(self):
        engine = AlertEngine(redis_client=None)
        prediction = make_prediction()

        alerts = []
        for _ in range(MATERIAL_RISK_ZERO_DAYS):
            alerts = engine.evaluate(prediction, make_record(material_deliveries=0))

        assert alert_of_type(alerts, "MATERIAL_RISK") is not None

    def test_does_not_fire_before_threshold(self):
        engine = AlertEngine(redis_client=None)
        prediction = make_prediction()

        alerts = []
        for _ in range(MATERIAL_RISK_ZERO_DAYS - 1):
            alerts = engine.evaluate(prediction, make_record(material_deliveries=0))

        assert alert_of_type(alerts, "MATERIAL_RISK") is None

    def test_streak_resets_on_delivery(self):
        engine = AlertEngine(redis_client=None)
        prediction = make_prediction()

        for _ in range(MATERIAL_RISK_ZERO_DAYS - 1):
            engine.evaluate(prediction, make_record(material_deliveries=0))

        # A delivery resets the streak
        engine.evaluate(prediction, make_record(material_deliveries=2))
        alerts = engine.evaluate(prediction, make_record(material_deliveries=0))
        assert alert_of_type(alerts, "MATERIAL_RISK") is None

    def test_severity_is_critical(self):
        engine = AlertEngine(redis_client=None)
        prediction = make_prediction()

        alerts = []
        for _ in range(MATERIAL_RISK_ZERO_DAYS):
            alerts = engine.evaluate(prediction, make_record(material_deliveries=0))

        alert = alert_of_type(alerts, "MATERIAL_RISK")
        assert alert is not None
        assert alert["severity"] == "critical"


# ---------------------------------------------------------------------------
# REWORK_SPIKE tests
# ---------------------------------------------------------------------------

class TestReworkSpike:

    def test_fires_above_threshold(self, engine):
        high_rate = REWORK_SPIKE_RATE + 1.0
        record = make_record(rework_rate=high_rate)
        alerts = engine.evaluate(make_prediction(), record)
        assert alert_of_type(alerts, "REWORK_SPIKE") is not None

    def test_does_not_fire_at_threshold(self, engine):
        record = make_record(rework_rate=REWORK_SPIKE_RATE)
        alerts = engine.evaluate(make_prediction(), record)
        assert alert_of_type(alerts, "REWORK_SPIKE") is None

    def test_does_not_fire_below_threshold(self, engine):
        record = make_record(rework_rate=REWORK_SPIKE_RATE - 1.0)
        alerts = engine.evaluate(make_prediction(), record)
        assert alert_of_type(alerts, "REWORK_SPIKE") is None

    def test_message_contains_rate(self, engine):
        high_rate = REWORK_SPIKE_RATE + 2.5
        record = make_record(rework_rate=high_rate)
        alerts = engine.evaluate(make_prediction(), record)
        alert = alert_of_type(alerts, "REWORK_SPIKE")
        assert str(round(high_rate, 1)) in alert["message"]


# ---------------------------------------------------------------------------
# Multiple alerts in one evaluation
# ---------------------------------------------------------------------------

class TestMultipleAlerts:

    def test_multiple_conditions_can_fire_simultaneously(self):
        engine = AlertEngine(redis_client=None)
        prediction = make_prediction(delay_risk="high")

        # Low SPI + zero deliveries — build up streak for both
        low_spi = SCHEDULE_SLIP_SPI - 0.01

        for _ in range(max(SCHEDULE_SLIP_CONSECUTIVE, MATERIAL_RISK_ZERO_DAYS) - 1):
            engine.evaluate(
                make_prediction(delay_risk="low"),
                make_record(spi=low_spi, material_deliveries=0),
            )

        # Final evaluation with high risk also set
        alerts = engine.evaluate(
            prediction,
            make_record(
                spi=low_spi,
                material_deliveries=0,
                rolling_progress_rate=0.0,
                rework_rate=REWORK_SPIKE_RATE + 1.0,
            ),
        )

        types = {a["type"] for a in alerts}
        assert "DELAY_WARNING" in types


# ---------------------------------------------------------------------------
# Redis publish tests
# ---------------------------------------------------------------------------

class TestPublishAlert:

    @pytest.mark.asyncio
    async def test_publish_alert_calls_redis(self):
        mock_redis = AsyncMock()
        engine = AlertEngine(redis_client=mock_redis)

        alert = {
            "alert_id": "abc-123",
            "project_id": "proj-test",
            "type": "DELAY_WARNING",
            "severity": "critical",
            "message": "Test",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "recommended_action": "Review site",
        }

        await engine.publish_alert(alert)

        mock_redis.publish.assert_awaited_once()
        channel_arg = mock_redis.publish.call_args[0][0]
        assert channel_arg == "alerts.proj-test"

    @pytest.mark.asyncio
    async def test_publish_skipped_when_no_redis(self):
        engine = AlertEngine(redis_client=None)
        alert = {"project_id": "proj-test", "type": "DELAY_WARNING"}
        # Should not raise even with no Redis
        await engine.publish_alert(alert)
