"""JSON structured logger for Component 01."""

import logging
import json
import os
from datetime import datetime, timezone


class _JSONFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects."""

    def __init__(self, module_name: str) -> None:
        super().__init__()
        self._module_name = module_name

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "component": "C01",
            "module": self._module_name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def get_logger(name: str) -> logging.Logger:
    """Returns a JSON-structured logger that writes to stdout.

    Args:
        name: Module name embedded in every log record.

    Returns:
        logging.Logger: Configured logger instance.
    """
    logger = logging.getLogger(f"c01.{name}")
    if logger.handlers:
        return logger

    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logger.setLevel(level)

    handler = logging.StreamHandler()
    handler.setFormatter(_JSONFormatter(name))
    logger.addHandler(handler)
    logger.propagate = False
    return logger
