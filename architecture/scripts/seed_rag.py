"""
seed_rag.py — Seeds the Supabase ``sl_residential_plans`` RAG store used by
Stage 3 (stages/stage3_floor_plan/rag_retriever.py).

Two modes:
  samples   insert the six built-in sample plan descriptions with embeddings
  backfill  embed every existing row whose ``embedding`` is still null

Run from architecture/:
    uv run python scripts/seed_rag.py samples
    uv run python scripts/seed_rag.py backfill

Needs SUPABASE_URL and SUPABASE_KEY in architecture/.env.
"""

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

TABLE = "sl_residential_plans"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

SAMPLE_DESCRIPTIONS = [
    "3-bedroom single storey house in Batticaloa district, coastal location, 120 sqm footprint, modern style. Living room faces south toward road. Dining and kitchen at rear. Three bedrooms with one shared bathroom and one attached. Elevated foundation 600mm above ground level for coastal flood protection. Aluminum windows for salt air resistance.",
    "2-bedroom single storey house in Matara district, coastal location, 100 sqm footprint, traditional style. Front verandah facing road. Central living room. Kitchen at rear with separate washing area. Two bedrooms side by side. Clay tile roof with 45 degree pitch. Garden wall for privacy from road.",
    "5-bedroom two storey house in Colombo district, coastal location, 200 sqm footprint, modern style. Ground floor living, dining, kitchen and one bedroom. Upper floor four bedrooms with three bathrooms. Double garage. Flat concrete roof with parapet. Large balcony on upper floor facing the sea.",
    "3-bedroom two storey house in Hambantota district, coastal location, 140 sqm footprint, contemporary style. Open plan ground floor. Upper floor three bedrooms. Solar panels on roof. Rainwater harvesting tank. Cross-ventilation through louvered windows on all sides.",
    "2-bedroom single storey house in Puttalam district, coastal location, 90 sqm footprint, traditional style. Verandah at front. Living room central. Two bedrooms at rear. Kitchen connected to backyard. Coconut timber roof structure with clay tiles. Low boundary wall with gate facing the road.",
    "4-bedroom two storey house in Negombo, coastal location, 160 sqm footprint, modern style. Ground floor open plan living and kitchen. Upper floor four bedrooms two bathrooms. Roof terrace for sea views. Concrete block construction with plastered finish. Louvered windows for coastal breeze.",
]


def _connect():
    from sentence_transformers import SentenceTransformer
    from supabase import create_client

    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_KEY", "")
    if not url or not key:
        raise SystemExit("Missing SUPABASE_URL / SUPABASE_KEY in architecture/.env")
    return create_client(url, key), SentenceTransformer(EMBEDDING_MODEL)


def insert_samples() -> None:
    client, model = _connect()
    print(f"Inserting {len(SAMPLE_DESCRIPTIONS)} descriptions with embeddings...")
    for i, text in enumerate(SAMPLE_DESCRIPTIONS, 1):
        client.table(TABLE).insert({
            "content": text,
            "metadata": {},
            "embedding": model.encode(text).tolist(),
        }).execute()
        print(f"Inserted description {i}/{len(SAMPLE_DESCRIPTIONS)}")
    print("Done — all descriptions added with embeddings.")


def backfill_embeddings() -> None:
    client, model = _connect()
    rows = client.table(TABLE).select("id,content").is_("embedding", "null").execute()
    print(f"Rows without embedding: {len(rows.data)}")
    for row in rows.data:
        embedding = model.encode(row["content"]).tolist()
        client.table(TABLE).update({"embedding": embedding}).eq("id", row["id"]).execute()
        print(f"Updated row {row['id']}")
    print("Done")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("mode", choices=["samples", "backfill"])
    args = parser.parse_args()
    insert_samples() if args.mode == "samples" else backfill_embeddings()
