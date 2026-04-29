"""ICTAD rate loader — reads schedule-of-rates data from PostgreSQL or flat CSV files.

The Institute for Construction Training and Development (ICTAD) publishes quarterly
unit rates for all civil and building works in Sri Lanka. This module abstracts
loading those rates from the backing store so the rest of the pipeline is
storage-agnostic.
"""

import csv
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Default CSV directory relative to this file when the DB is not available
_DEFAULT_RATES_DIR = Path(__file__).parent.parent.parent / "data" / "ictad_rates"

# Fallback hardcoded rates (LKR per unit) used when no data file is present.
# These are indicative 2024-Q4 values only — replace with live ICTAD data.
_FALLBACK_RATES: dict[str, dict] = {
    "foundation_excavation_m3": {
        "unit": "m³", "rate_lkr": 3_500.0, "description": "Excavation in ordinary soil"
    },
    "blinding_concrete_m3": {
        "unit": "m³", "rate_lkr": 38_000.0, "description": "Plain concrete C10 blinding"
    },
    "foundation_concrete_m3": {
        "unit": "m³", "rate_lkr": 62_000.0, "description": "Reinforced concrete C25 foundation"
    },
    "rc_columns_m3": {
        "unit": "m³", "rate_lkr": 95_000.0, "description": "RC columns C30 including formwork"
    },
    "rc_slab_m3": {
        "unit": "m³", "rate_lkr": 88_000.0, "description": "RC suspended slab C25"
    },
    "external_brickwork_m3": {
        "unit": "m³", "rate_lkr": 28_000.0, "description": "225mm solid brick wall"
    },
    "internal_blockwork_m3": {
        "unit": "m³", "rate_lkr": 22_000.0, "description": "115mm concrete block partition"
    },
    "roof_area_sqm": {
        "unit": "m²", "rate_lkr": 4_500.0, "description": "Roof covering incl. structure"
    },
    "floor_tile_sqm": {
        "unit": "m²", "rate_lkr": 3_800.0, "description": "Ceramic floor tile 300×300"
    },
    "wall_plaster_sqm": {
        "unit": "m²", "rate_lkr": 850.0, "description": "Sand-cement plaster 13mm"
    },
    "ceiling_sqm": {
        "unit": "m²", "rate_lkr": 1_200.0, "description": "PVC ceiling panel"
    },
    "door_count": {
        "unit": "nr", "rate_lkr": 45_000.0, "description": "Solid timber door set"
    },
    "window_count": {
        "unit": "nr", "rate_lkr": 28_000.0, "description": "Aluminium sliding window"
    },
    "paint_sqm": {
        "unit": "m²", "rate_lkr": 350.0, "description": "Two coats emulsion paint"
    },
    "electrical_points": {
        "unit": "point", "rate_lkr": 4_500.0, "description": "Wiring point complete"
    },
    "total_plumbing_fixtures": {
        "unit": "nr", "rate_lkr": 12_000.0, "description": "Plumbing fixture installed"
    },
    "steel_kg_estimate": {
        "unit": "kg", "rate_lkr": 260.0, "description": "Reinforcement steel Y-bar"
    },
}


class ICTADLoader:
    """Loads ICTAD unit rates from PostgreSQL or local CSV files.

    Priority order:
      1. PostgreSQL (if DATABASE_URL env var is set)
      2. CSV files in data/ictad_rates/
      3. Hardcoded fallback rates
    """

    def __init__(self, rates_dir: Optional[Path] = None) -> None:
        self._rates_dir = rates_dir or _DEFAULT_RATES_DIR
        self._cache: dict[str, dict] = {}

    def load_all(self) -> dict[str, dict]:
        """Load the full rate schedule and return it as a dict keyed by item code.

        Returns:
            Dict mapping BOQ item key -> {'unit': str, 'rate_lkr': float, 'description': str}.
        """
        if self._cache:
            return self._cache

        db_url = os.getenv("DATABASE_URL")
        if db_url:
            self._cache = self._load_from_db(db_url)
        else:
            self._cache = self._load_from_csv()

        if not self._cache:
            logger.warning("No ICTAD rate source available — using hardcoded fallback rates.")
            self._cache = dict(_FALLBACK_RATES)

        return self._cache

    def get_rate(self, item_key: str) -> float:
        """Return the LKR unit rate for a given BOQ item key.

        Args:
            item_key: BOQ quantity key, e.g. 'rc_slab_m3'.

        Returns:
            Unit rate in LKR, or 0.0 if not found.
        """
        rates = self.load_all()
        entry = rates.get(item_key, {})
        rate = float(entry.get("rate_lkr", 0.0))
        if rate == 0.0:
            logger.warning("No rate found for item '%s'.", item_key)
        return rate

    def get_rates_for_district_view(self, district: str) -> list[dict]:
        """Return all rates formatted for the GET /rates/{district} endpoint.

        The district multiplier is NOT applied here — that is done in RateEngine.
        This method returns the raw ICTAD schedule.
        """
        rates = self.load_all()
        return [
            {
                "item_key": key,
                "description": v.get("description", ""),
                "unit": v.get("unit", ""),
                "base_rate_lkr": v.get("rate_lkr", 0.0),
            }
            for key, v in rates.items()
        ]

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _load_from_db(self, db_url: str) -> dict[str, dict]:
        """Load rates from PostgreSQL.

        TODO: Implement SQLAlchemy query against the ictad_rates table.
        Expected schema:
          CREATE TABLE ictad_rates (
            item_key TEXT PRIMARY KEY,
            description TEXT,
            unit TEXT,
            rate_lkr NUMERIC,
            effective_date DATE
          );
        """
        logger.info("Loading ICTAD rates from PostgreSQL.")
        try:
            # TODO: Replace with real SQLAlchemy session
            raise NotImplementedError("PostgreSQL loader not yet implemented.")
        except Exception as exc:
            logger.error("DB load failed (%s) — falling back to CSV.", exc)
            return {}

    def _load_from_csv(self) -> dict[str, dict]:
        """Load rates from CSV files in the rates directory.

        Expected filename: ictad_rates_<year>_Q<quarter>.csv
        Expected columns: item_key, description, unit, rate_lkr
        """
        if not self._rates_dir.exists():
            logger.warning("Rates directory %s does not exist.", self._rates_dir)
            return {}

        csv_files = sorted(self._rates_dir.glob("*.csv"), reverse=True)
        if not csv_files:
            logger.warning("No CSV rate files found in %s.", self._rates_dir)
            return {}

        latest = csv_files[0]
        logger.info("Loading ICTAD rates from %s.", latest)
        rates: dict[str, dict] = {}
        with latest.open(newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                key = row.get("item_key", "").strip()
                if not key:
                    continue
                rates[key] = {
                    "description": row.get("description", ""),
                    "unit": row.get("unit", ""),
                    "rate_lkr": float(row.get("rate_lkr", 0.0)),
                }
        return rates
