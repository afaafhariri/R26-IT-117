import os
from pathlib import Path

from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from supabase import create_client

load_dotenv(Path(__file__).resolve().parent / ".env")

supabase_url = os.getenv("SUPABASE_URL", "")
supabase_key = os.getenv("SUPABASE_KEY", "")
if not supabase_url or not supabase_key:
    raise SystemExit("Missing SUPABASE_URL / SUPABASE_KEY in .env")

client = create_client(supabase_url, supabase_key)
model = SentenceTransformer('all-MiniLM-L6-v2')

rows = client.table('sl_residential_plans').select('id,content').is_('embedding', 'null').execute()
print(f'Rows without embedding: {len(rows.data)}')

for row in rows.data:
    embedding = model.encode(row['content']).tolist()
    client.table('sl_residential_plans').update({'embedding': embedding}).eq('id', row['id']).execute()
    print(f'Updated row {row["id"]}')

print('Done')
