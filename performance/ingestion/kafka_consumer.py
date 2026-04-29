"""
Kafka consumer for real-time construction progress events.

Subscribes to the "construction.progress" topic and feeds each message
through the normalisation and prediction pipeline without blocking the
FastAPI event loop (runs in a dedicated daemon thread).
"""

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from confluent_kafka import Consumer, KafkaError, KafkaException

from ingestion.progress_normaliser import ProgressNormaliser

if TYPE_CHECKING:
    from main import AppState

logger = logging.getLogger(__name__)

TOPIC = "construction.progress"
POLL_TIMEOUT_SEC = 1.0
RETRY_BACKOFF_SEC = 5


class ProgressKafkaConsumer:
    """
    Wraps a Confluent Kafka consumer.

    Lifecycle:
        consumer = ProgressKafkaConsumer(bootstrap_servers=..., app_state=...)
        thread = threading.Thread(target=consumer.start, daemon=True)
        thread.start()
    """

    def __init__(self, bootstrap_servers: str, app_state: "AppState") -> None:
        self._bootstrap_servers = bootstrap_servers
        self._app_state = app_state
        self._normaliser = ProgressNormaliser()
        self._running = False

        self._consumer_config = {
            "bootstrap.servers": bootstrap_servers,
            "group.id": os.getenv("KAFKA_GROUP_ID", "performance-monitor-group"),
            "auto.offset.reset": os.getenv("KAFKA_AUTO_OFFSET_RESET", "latest"),
            "enable.auto.commit": True,
            "auto.commit.interval.ms": 5000,
            # Security — populated from env when a secured cluster is used.
            # TODO: add SSL/SASL config blocks for production.
            **self._security_config(),
        }

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def start(self) -> None:
        """
        Start consuming messages in an infinite loop.
        Call this method inside a daemon thread — it blocks until the
        process exits or an unrecoverable error occurs.
        """
        self._running = True
        logger.info("Kafka consumer starting. Topic: %s, Servers: %s", TOPIC, self._bootstrap_servers)

        while self._running:
            try:
                self._consume_loop()
            except KafkaException as exc:
                logger.error("Kafka error — retrying in %ds: %s", RETRY_BACKOFF_SEC, exc)
                time.sleep(RETRY_BACKOFF_SEC)
            except Exception as exc:  # pylint: disable=broad-except
                logger.exception("Unexpected consumer error — retrying in %ds: %s", RETRY_BACKOFF_SEC, exc)
                time.sleep(RETRY_BACKOFF_SEC)

    def stop(self) -> None:
        """Signal the consume loop to exit gracefully."""
        self._running = False

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _consume_loop(self) -> None:
        consumer = Consumer(self._consumer_config)
        consumer.subscribe([TOPIC])
        logger.info("Subscribed to Kafka topic: %s", TOPIC)

        try:
            while self._running:
                msg = consumer.poll(timeout=POLL_TIMEOUT_SEC)
                if msg is None:
                    continue
                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        logger.debug("End of partition reached: %s [%d]", msg.topic(), msg.partition())
                    else:
                        raise KafkaException(msg.error())
                else:
                    self.on_message(msg)
        finally:
            consumer.close()
            logger.info("Kafka consumer closed")

    def on_message(self, message) -> None:
        """
        Process a single Kafka message.

        Expected JSON schema::

            {
                "project_id": str,
                "timestamp": ISO-8601 str,
                "phase": str,
                "planned_completion_pct": float,
                "actual_completion_pct": float,
                "labour_count": int,
                "material_deliveries": int,
                "weather_delay_days": int,
                "rework_incidents": int
            }
        """
        try:
            raw_bytes = message.value()
            if raw_bytes is None:
                logger.warning("Received null Kafka message — skipping")
                return

            payload: dict = json.loads(raw_bytes.decode("utf-8"))
            logger.debug("Received message for project %s", payload.get("project_id"))

            # Ensure timestamp is datetime-aware
            ts = payload.get("timestamp")
            if isinstance(ts, str):
                payload["timestamp"] = datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)
            elif ts is None:
                payload["timestamp"] = datetime.now(timezone.utc)

            normalised = self._normaliser.normalise(payload)
            project_id = normalised.get("project_id")

            if project_id:
                self._app_state.progress_store.setdefault(project_id, []).append(normalised)
                logger.info(
                    "Stored normalised record for project %s — SPI=%.3f, delayed=%s",
                    project_id,
                    normalised.get("schedule_performance_index", 0.0),
                    normalised.get("is_delayed"),
                )
            else:
                logger.warning("Message missing project_id — skipped")

        except json.JSONDecodeError as exc:
            logger.error("Invalid JSON in Kafka message: %s", exc)
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("Failed to process Kafka message: %s", exc)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _security_config() -> dict:
        """
        Returns SASL/SSL config when env vars are present.
        Leave env vars unset for local plaintext clusters.
        """
        protocol = os.getenv("KAFKA_SECURITY_PROTOCOL", "PLAINTEXT")
        config: dict = {"security.protocol": protocol}

        if protocol in ("SASL_PLAINTEXT", "SASL_SSL"):
            config.update(
                {
                    "sasl.mechanism": os.getenv("KAFKA_SASL_MECHANISM", "PLAIN"),
                    "sasl.username": os.getenv("KAFKA_SASL_USERNAME", ""),
                    "sasl.password": os.getenv("KAFKA_SASL_PASSWORD", ""),
                }
            )
        if protocol in ("SSL", "SASL_SSL"):
            ssl_ca = os.getenv("KAFKA_SSL_CA_LOCATION")
            if ssl_ca:
                config["ssl.ca.location"] = ssl_ca
            # TODO: add client cert paths if mutual TLS is required.

        return config
