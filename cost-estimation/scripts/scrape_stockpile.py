#!/usr/bin/env python
"""Stockpile.lk material price scraper — scheduled background job.

Never called from the request path. Run manually or via cron:

    python scripts/scrape_stockpile.py            # scrape, update overlay
    python scripts/scrape_stockpile.py --dry-run  # scrape, print, write nothing

Flow per category page:
  1. Fetch the server-rendered Magento product grid (all products, one request).
  2. Classify each product into a (part_key, material_key) via keyword rules.
  3. Normalise price to the catalog unit where a unit_factor is known;
     otherwise the sample is recorded in price history only.
  4. Per (part, material): drop outliers, take the median supply price.
  5. Median within ±MAX_DEVIATION of the seed supply rate -> written to
     data/scraped_prices/current_prices.csv (the overlay MaterialCatalog reads).
     Outside that band -> data/scraped_prices/review_queue.csv for a human.
  All raw samples are appended to data/scraped_prices/price_history.csv —
  this time series is future training data for the CCPI escalation model.
"""

import argparse
import csv
import logging
import re
import statistics
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
from bs4 import BeautifulSoup

logging.basicConfig(level="INFO", format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("scrape_stockpile")

BASE_URL = "https://stockpile.lk"
USER_AGENT = "R26-IT-117-cost-research/0.1 (academic project; contact repo owner)"
REQUEST_DELAY_S = 2.5
REQUEST_TIMEOUT_S = 30.0

DATA_DIR = Path(__file__).parent.parent / "data"
CATALOG_CSV = DATA_DIR / "material_catalog" / "material_catalog.csv"
SCRAPED_DIR = DATA_DIR / "scraped_prices"
HISTORY_CSV = SCRAPED_DIR / "price_history.csv"
OVERLAY_CSV = SCRAPED_DIR / "current_prices.csv"
REVIEW_CSV = SCRAPED_DIR / "review_queue.csv"

# Reject a scraped median that moves more than this fraction from the seed
# supply rate — one bad parse must not silently swing every estimate.
MAX_DEVIATION = 0.50
# Within one (part, material) group, drop samples outside this band around
# the group median before computing the final median.
OUTLIER_LOW, OUTLIER_HIGH = 0.25, 4.0

# Products whose name matches this are ignored entirely (accessories, spares).
SKIP_RE = re.compile(
    r"frame|lock|handle|hinge|accessor|bracket|screw|channel|gasket|sealant|glue",
    re.IGNORECASE,
)

# Classification rules per category page. Each rule: (regex, part_key,
# material_key, unit_factor). unit_factor converts the listed price to the
# catalog unit (price_per_unit = raw_price * unit_factor); None means the
# listing unit is unknown/incompatible — record history only, never overlay.
CATEGORY_RULES: dict[str, list[tuple[re.Pattern, str, str, Optional[float]]]] = {
    "/en/door-windows.html": [
        (re.compile(r"teak.*door|door.*teak", re.I), "door_count", "solid_timber_teak", 1.0),
        (re.compile(r"plywood.*door|door.*plywood", re.I), "door_count", "plywood_flush", 1.0),
        (re.compile(r"composite.*door|door.*composite", re.I), "door_count", "wood_composite", 1.0),
        (re.compile(r"tempered\s+glass\s+door", re.I), "door_count", "tempered_glass_12mm", 1.0),
        (re.compile(r"aluminium.*door|aluminum.*door", re.I), "door_count", "aluminium_glazed", 1.0),
        (re.compile(r"aluminium.*window|aluminum.*window", re.I), "window_count", "aluminium_sliding", 1.0),
        (re.compile(r"upvc.*window", re.I), "window_count", "upvc_sliding", 1.0),
        (re.compile(r"timber.*window|wood(en)?.*window", re.I), "window_count", "timber_casement", 1.0),
        (re.compile(r"steel.*window", re.I), "window_count", "steel_framed", 1.0),
    ],
    "/en/roofing-ceiling.html": [
        # Sheet goods are listed per sheet/foot in unknown sizes — history only.
        (re.compile(r"fib(er|re)\s*cement.*sheet", re.I), "roof_area_sqm", "fiber_cement_sheet", None),
        (re.compile(r"zinc|zn.?al|alu.?zinc", re.I), "roof_area_sqm", "zinc_alum_sheet", None),
        (re.compile(r"clay.*tile", re.I), "roof_area_sqm", "clay_tile", None),
        (re.compile(r"concrete.*tile", re.I), "roof_area_sqm", "concrete_tile", None),
        # 2'x2' ceiling tile = 0.3716 m² -> per-m² price = per-tile price / 0.3716
        (re.compile(r"mineral\s*fib(er|re).*(ceiling|tile)", re.I), "ceiling_sqm", "mineral_fiber_tile", 1 / 0.3716),
        (re.compile(r"gypsum", re.I), "ceiling_sqm", "gypsum_board", None),
        (re.compile(r"pvc.*ceiling|ceiling.*pvc", re.I), "ceiling_sqm", "pvc_panel", None),
        (re.compile(r"fib(er|re)\s*glass.*ceiling", re.I), "ceiling_sqm", "fiberglass_panel", None),
    ],
}

_PRICE_RE = re.compile(r"Rs\.?\s*([\d,]+(?:\.\d{1,2})?)")


def fetch_category(client: httpx.Client, path: str) -> Optional[str]:
    """Fetch one category page with all products on a single page."""
    url = f"{BASE_URL}{path}?product_list_limit=all"
    try:
        resp = client.get(url)
        resp.raise_for_status()
        return resp.text
    except httpx.HTTPError as exc:
        logger.error("Fetch failed for %s: %s", url, exc)
        return None


def parse_products(html: str) -> list[dict]:
    """Extract (name, price, url, supplier) from a Magento product grid."""
    soup = BeautifulSoup(html, "html.parser")
    products = []
    for item in soup.select("li.item.product.product-item"):
        link = item.select_one("a.product-item-link") or item.select_one(".product-item-name a")
        name = link.get_text(strip=True) if link else ""
        url = link.get("href", "") if link else ""

        price = None
        price_el = item.select_one("[data-price-amount]")
        if price_el is not None:
            try:
                price = float(price_el["data-price-amount"])
            except (ValueError, KeyError):
                price = None
        if price is None:
            m = _PRICE_RE.search(item.get_text(" ", strip=True))
            if m:
                price = float(m.group(1).replace(",", ""))

        supplier_el = item.select_one(".product-item-brand, .supplier-name, .product-item-vendor")
        supplier = supplier_el.get_text(strip=True) if supplier_el else ""

        if name and price and price > 0:
            products.append({"name": name, "price": price, "url": url, "supplier": supplier})
    return products


def classify(name: str, rules: list) -> Optional[tuple[str, str, Optional[float]]]:
    """Map a product name to (part_key, material_key, unit_factor), or None."""
    if SKIP_RE.search(name):
        return None
    for pattern, part_key, material_key, unit_factor in rules:
        if pattern.search(name):
            return part_key, material_key, unit_factor
    return None


def reject_outliers(prices: list[float]) -> list[float]:
    """Drop samples far outside the group median."""
    if len(prices) < 3:
        return prices
    med = statistics.median(prices)
    return [p for p in prices if OUTLIER_LOW * med <= p <= OUTLIER_HIGH * med]


def load_seed_supply_rates() -> dict[tuple[str, str], float]:
    """Seed supply rate (installed rate minus install cost) per (part, material)."""
    rates: dict[tuple[str, str], float] = {}
    with CATALOG_CSV.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            key = (row["part_key"], row["material_key"])
            rates[key] = float(row["rate_lkr"]) - float(row["install_cost_lkr"])
    return rates


def scrape(categories: list[str]) -> list[dict]:
    """Scrape all configured categories and return classified samples."""
    samples: list[dict] = []
    scraped_at = datetime.now(tz=timezone.utc).isoformat(timespec="seconds")

    with httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT_S,
        follow_redirects=True,
    ) as client:
        for i, path in enumerate(categories):
            if i > 0:
                time.sleep(REQUEST_DELAY_S)
            logger.info("Fetching %s ...", path)
            html = fetch_category(client, path)
            if html is None:
                continue

            products = parse_products(html)
            rules = CATEGORY_RULES[path]
            matched = 0
            for product in products:
                result = classify(product["name"], rules)
                if result is None:
                    continue
                part_key, material_key, unit_factor = result
                normalized = (
                    round(product["price"] * unit_factor, 2)
                    if unit_factor is not None else None
                )
                samples.append({
                    "scraped_at": scraped_at,
                    "part_key": part_key,
                    "material_key": material_key,
                    "product_name": product["name"],
                    "supplier": product["supplier"],
                    "raw_price_lkr": product["price"],
                    "unit_factor": unit_factor if unit_factor is not None else "",
                    "normalized_rate_lkr": normalized if normalized is not None else "",
                    "url": product["url"],
                })
                matched += 1
            logger.info("%s: %d products, %d classified.", path, len(products), matched)
    return samples


def build_overlay(samples: list[dict]) -> tuple[list[dict], list[dict]]:
    """Aggregate normalised samples into overlay rows + review-queue rows."""
    seed_supply = load_seed_supply_rates()
    today = str(date.today())

    groups: dict[tuple[str, str], list[float]] = {}
    for s in samples:
        if s["normalized_rate_lkr"] == "":
            continue
        groups.setdefault((s["part_key"], s["material_key"]), []).append(
            float(s["normalized_rate_lkr"])
        )

    overlay_rows, review_rows = [], []
    for (part_key, material_key), prices in sorted(groups.items()):
        kept = reject_outliers(prices)
        if not kept:
            continue
        median = round(statistics.median(kept), 2)
        seed = seed_supply.get((part_key, material_key), 0.0)

        row = {
            "part_key": part_key,
            "material_key": material_key,
            "supply_rate_lkr": median,
            "sample_count": len(kept),
            "last_updated": today,
            "source": "stockpile.lk",
        }
        if seed > 0 and abs(median - seed) / seed > MAX_DEVIATION:
            row["seed_supply_rate_lkr"] = seed
            row["deviation_pct"] = round(100 * (median - seed) / seed, 1)
            review_rows.append(row)
            logger.warning(
                "REVIEW %s/%s: median %.0f deviates %.0f%% from seed %.0f — not applied.",
                part_key, material_key, median, row["deviation_pct"], seed,
            )
        else:
            overlay_rows.append(row)
    return overlay_rows, review_rows


def append_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    exists = path.exists()
    with path.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        if not exists:
            writer.writeheader()
        writer.writerows(rows)


def write_overlay(rows: list[dict]) -> None:
    """Replace the overlay with the latest medians (full rewrite, not append)."""
    fieldnames = ["part_key", "material_key", "supply_rate_lkr",
                  "sample_count", "last_updated", "source"]
    with OVERLAY_CSV.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true",
                        help="Scrape and report, but write no files.")
    parser.add_argument("--category", action="append", choices=list(CATEGORY_RULES),
                        help="Limit to specific category paths (repeatable).")
    args = parser.parse_args()

    categories = args.category or list(CATEGORY_RULES)
    samples = scrape(categories)
    if not samples:
        logger.error("No samples scraped — site structure may have changed.")
        return 1

    overlay_rows, review_rows = build_overlay(samples)

    logger.info("Samples: %d total, %d normalisable.", len(samples),
                sum(1 for s in samples if s["normalized_rate_lkr"] != ""))
    for row in overlay_rows:
        logger.info("OVERLAY %s/%s = %.0f LKR (n=%d)", row["part_key"],
                    row["material_key"], row["supply_rate_lkr"], row["sample_count"])

    if args.dry_run:
        logger.info("Dry run — nothing written.")
        return 0

    SCRAPED_DIR.mkdir(parents=True, exist_ok=True)
    history_fields = ["scraped_at", "part_key", "material_key", "product_name",
                      "supplier", "raw_price_lkr", "unit_factor",
                      "normalized_rate_lkr", "url"]
    append_csv(HISTORY_CSV, samples, history_fields)
    if overlay_rows:
        write_overlay(overlay_rows)
    if review_rows:
        review_fields = ["part_key", "material_key", "supply_rate_lkr", "sample_count",
                         "last_updated", "source", "seed_supply_rate_lkr", "deviation_pct"]
        append_csv(REVIEW_CSV, review_rows, review_fields)

    logger.info("Wrote %d history rows, %d overlay rows, %d review rows.",
                len(samples), len(overlay_rows), len(review_rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
