"""File I/O utilities for Component 01 uploads and schema loading."""

import json
import os
import uuid
from pathlib import Path

from utils.logger import get_logger

_logger = get_logger("file_handler")
_TMP_DIR = Path("/tmp/r26")
_schema_cache: dict[str, dict] = {}


class FileHandler:
    """Handles temporary file persistence for uploaded cadastral plans."""

    def save_upload(self, file_bytes: bytes, filename: str, suffix: str) -> Path:
        """Saves an uploaded file to a temporary location.

        Args:
            file_bytes: Raw file content.
            filename: Original filename (used in the saved path for traceability).
            suffix: File extension including the leading dot, e.g. ``".pdf"``.

        Returns:
            Path: Absolute path to the saved temporary file.
        """
        _TMP_DIR.mkdir(parents=True, exist_ok=True)
        unique_name = f"{uuid.uuid4().hex}_{filename}"
        dest = _TMP_DIR / unique_name
        dest.write_bytes(file_bytes)
        _logger.info("Saved upload: %s (%d bytes)", dest, len(file_bytes))
        return dest

    def cleanup(self, file_path: Path) -> None:
        """Deletes a temporary file after processing.

        Args:
            file_path: Path to the file that should be removed.
        """
        try:
            file_path.unlink()
            _logger.info("Cleaned up temp file: %s", file_path)
        except FileNotFoundError:
            _logger.warning("Temp file not found during cleanup: %s", file_path)

    def load_schema(self, schema_name: str) -> dict:
        """Loads a JSON schema by name, caching after first read.

        Args:
            schema_name: Filename (without path) of the schema, e.g. ``"site_schema.json"``.

        Returns:
            dict: Parsed JSON schema object.

        Raises:
            FileNotFoundError: If the schema file does not exist.
            json.JSONDecodeError: If the file is not valid JSON.
        """
        if schema_name in _schema_cache:
            return _schema_cache[schema_name]

        schema_dir = Path(os.getenv("SCHEMA_DIR", "shared/schemas"))
        schema_path = schema_dir / schema_name

        if not schema_path.exists():
            _logger.error("Schema not found: %s", schema_path)
            raise FileNotFoundError(f"Schema file not found: {schema_path}")

        with schema_path.open("r", encoding="utf-8") as fh:
            schema = json.load(fh)

        _schema_cache[schema_name] = schema
        _logger.info("Loaded schema: %s", schema_name)
        return schema
