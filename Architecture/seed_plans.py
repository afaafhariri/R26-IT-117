from sentence_transformers import SentenceTransformer
from supabase import create_client

client = create_client(
    'https://huljdcykcuuwxmlkhnxc.supabase.co',
    'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imh1bGpkY3lrY3V1d3htbGtobnhjIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Nzc1Nzk0MTMsImV4cCI6MjA5MzE1NTQxM30.o1h4pkpPW0mpIjBy-QmTaE40xHaAc9YgmKjQPwOQJhM'
)
model = SentenceTransformer('all-MiniLM-L6-v2')

descriptions = [
    "3-bedroom single storey house in Batticaloa district, coastal location, 120 sqm footprint, modern style. Living room faces south toward road. Dining and kitchen at rear. Three bedrooms with one shared bathroom and one attached. Elevated foundation 600mm above ground level for coastal flood protection. Aluminum windows for salt air resistance.",
    "2-bedroom single storey house in Matara district, coastal location, 100 sqm footprint, traditional style. Front verandah facing road. Central living room. Kitchen at rear with separate washing area. Two bedrooms side by side. Clay tile roof with 45 degree pitch. Garden wall for privacy from road.",
    "5-bedroom two storey house in Colombo district, coastal location, 200 sqm footprint, modern style. Ground floor living, dining, kitchen and one bedroom. Upper floor four bedrooms with three bathrooms. Double garage. Flat concrete roof with parapet. Large balcony on upper floor facing the sea.",
    "3-bedroom two storey house in Hambantota district, coastal location, 140 sqm footprint, contemporary style. Open plan ground floor. Upper floor three bedrooms. Solar panels on roof. Rainwater harvesting tank. Cross-ventilation through louvered windows on all sides.",
    "2-bedroom single storey house in Puttalam district, coastal location, 90 sqm footprint, traditional style. Verandah at front. Living room central. Two bedrooms at rear. Kitchen connected to backyard. Coconut timber roof structure with clay tiles. Low boundary wall with gate facing the road.",
    "4-bedroom two storey house in Negombo, coastal location, 160 sqm footprint, modern style. Ground floor open plan living and kitchen. Upper floor four bedrooms two bathrooms. Roof terrace for sea views. Concrete block construction with plastered finish. Louvered windows for coastal breeze.",
]

print(f"Inserting {len(descriptions)} descriptions with embeddings...")

for i, text in enumerate(descriptions, 1):
    embedding = model.encode(text).tolist()
    client.table('sl_residential_plans').insert({
        'content': text,
        'metadata': {},
        'embedding': embedding,
    }).execute()
    print(f"Inserted description {i}/{len(descriptions)}")

print("Done — all descriptions added with embeddings.")
