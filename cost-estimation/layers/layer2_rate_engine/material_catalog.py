"""Material catalog — 2-5 material variants per BOQ part with price overlay.

Each variant row carries an installed unit rate (supply + fix, same basis as the
ICTAD schedule). A scraped-price overlay CSV, produced by the background scraper
job (scripts/scrape_stockpile.py), can refresh the supply portion of a rate.
Overlay rows older than ``stale_days`` are ignored so a dead scraper can never
poison estimates — the seed rate is always the fallback.

Rate resolution per (part, material):
  1. Fresh overlay row  → supply_rate_lkr + seed install_cost_lkr
  2. Otherwise          → seed rate_lkr from the catalog CSV
"""

import csv
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).parent.parent.parent / "data"
_DEFAULT_CATALOG_CSV = _DATA_DIR / "material_catalog" / "material_catalog.csv"
_DEFAULT_OVERLAY_CSV = _DATA_DIR / "scraped_prices" / "current_prices.csv"

DEFAULT_STALE_DAYS = 45


def _parse_date(value: str) -> Optional[date]:
    try:
        return datetime.fromisoformat(value.strip()).date()
    except (ValueError, AttributeError):
        return None


class MaterialCatalog:
    """Loads material variants and resolves effective unit rates."""

    def __init__(
        self,
        catalog_csv: Optional[Path] = None,
        overlay_csv: Optional[Path] = None,
        stale_days: int = DEFAULT_STALE_DAYS,
    ) -> None:
        self._catalog_csv = catalog_csv or _DEFAULT_CATALOG_CSV
        self._overlay_csv = overlay_csv or _DEFAULT_OVERLAY_CSV
        self._stale_days = stale_days
        self._cache: Optional[dict[tuple[str, str], dict]] = None

    def load(self) -> dict[tuple[str, str], dict]:
        """Load seed catalog + fresh overlay rows, keyed by (part_key, material_key)."""
        if self._cache is not None:
            return self._cache

        entries = self._load_seed()
        self._apply_overlay(entries)
        self._cache = entries
        return entries

    def reload(self) -> None:
        """Drop the cache so the next access re-reads both CSVs."""
        self._cache = None

    def parts(self) -> list[str]:
        """All part keys that have material variants."""
        seen: list[str] = []
        for part_key, _ in self.load():
            if part_key not in seen:
                seen.append(part_key)
        return seen

    def variants(self, part_key: str) -> list[dict]:
        """All material variants for a part, cheapest first."""
        rows = [v for (p, _), v in self.load().items() if p == part_key]
        return sorted(rows, key=lambda r: r["rate_lkr"])

    def get(self, part_key: str, material_key: str) -> Optional[dict]:
        """Effective rate entry for one (part, material), or None if unknown."""
        return self.load().get((part_key, material_key))

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _load_seed(self) -> dict[tuple[str, str], dict]:
        if not self._catalog_csv.exists():
            logger.warning("Material catalog %s not found — variants disabled.", self._catalog_csv)
            return {}

        entries: dict[tuple[str, str], dict] = {}
        with self._catalog_csv.open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                part_key = row.get("part_key", "").strip()
                material_key = row.get("material_key", "").strip()
                if not part_key or not material_key:
                    continue
                entries[(part_key, material_key)] = {
                    "part_key": part_key,
                    "material_key": material_key,
                    "description": row.get("description", ""),
                    "unit": row.get("unit", ""),
                    "rate_lkr": float(row.get("rate_lkr", 0.0)),
                    "install_cost_lkr": float(row.get("install_cost_lkr", 0.0)),
                    "rate_source": row.get("source", "seed"),
                    "last_updated": row.get("last_updated", ""),
                }
        logger.info("Loaded %d material variants from %s.", len(entries), self._catalog_csv.name)
        return entries

    def _apply_overlay(self, entries: dict[tuple[str, str], dict]) -> None:
        """Overwrite supply rates from fresh scraped data; ignore stale rows."""
        if not self._overlay_csv.exists():
            return

        applied = stale = unknown = 0
        with self._overlay_csv.open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                key = (row.get("part_key", "").strip(), row.get("material_key", "").strip())
                entry = entries.get(key)
                if entry is None:
                    unknown += 1
                    continue

                updated = _parse_date(row.get("last_updated", ""))
                if updated is None or (date.today() - updated).days > self._stale_days:
                    stale += 1
                    continue

                try:
                    supply = float(row.get("supply_rate_lkr", 0.0))
                except ValueError:
                    continue
                if supply <= 0:
                    continue

                entry["rate_lkr"] = round(supply + entry["install_cost_lkr"], 2)
                entry["rate_source"] = row.get("source", "scraped")
                entry["last_updated"] = str(updated)
                applied += 1

        if applied or stale or unknown:
            logger.info(
                "Price overlay: %d applied, %d stale (> %d days, using seed), %d unknown keys.",
                applied, stale, self._stale_days, unknown,
            )
