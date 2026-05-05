from sentence_transformers import SentenceTransformer
from supabase import create_client

client = create_client(
    'https://huljdcykcuuwxmlkhnxc.supabase.co',
    'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imh1bGpkY3lrY3V1d3htbGtobnhjIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Nzc1Nzk0MTMsImV4cCI6MjA5MzE1NTQxM30.o1h4pkpPW0mpIjBy-QmTaE40xHaAc9YgmKjQPwOQJhM'
)
model = SentenceTransformer('all-MiniLM-L6-v2')

rows = client.table('sl_residential_plans').select('id,content').is_('embedding', 'null').execute()
print(f'Rows without embedding: {len(rows.data)}')

for row in rows.data:
    embedding = model.encode(row['content']).tolist()
    client.table('sl_residential_plans').update({'embedding': embedding}).eq('id', row['id']).execute()
    print(f'Updated row {row["id"]}')

print('Done')
