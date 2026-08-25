"""
embed_plans.py — Backfills embeddings for rows in the Supabase
sl_residential_plans RAG store that were inserted without one.

Run from Architecture/:
    python embed_plans.py

Requires SUPABASE_URL and SUPABASE_KEY in .env — see .env.example.
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Repo-root .env matches main.py; Architecture/.env matches seed_from_images.py.
# load_dotenv never overrides an already-set var, so the first hit wins.
_HERE = Path(__file__).resolve().parent
load_dotenv(_HERE.parent / ".env")
load_dotenv(_HERE / ".env")

from sentence_transformers import SentenceTransformer
from supabase import create_client

supabase_url = os.getenv("SUPABASE_URL", "")
supabase_key = os.getenv("SUPABASE_KEY", "")

if not all([supabase_url, supabase_key]):
    print("Missing SUPABASE_URL / SUPABASE_KEY in .env")
    sys.exit(1)

client = create_client(supabase_url, supabase_key)
model = SentenceTransformer("all-MiniLM-L6-v2")

rows = client.table('sl_residential_plans').select('id,content').is_('embedding', 'null').execute()
print(f'Rows without embedding: {len(rows.data)}')

for row in rows.data:
    embedding = model.encode(row['content']).tolist()
    client.table('sl_residential_plans').update({'embedding': embedding}).eq('id', row['id']).execute()
    print(f'Updated row {row["id"]}')

print('Done')
