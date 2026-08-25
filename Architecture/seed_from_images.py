"""
seed_from_images.py — Generates text descriptions of floor plan images using
Gemini Vision and seeds them into the Supabase sl_residential_plans RAG store.

Processes all PNG images from the CVC FPP dataset (X folder).
Skips images already inserted (checks metadata.source_file).

Run from Architecture/:
    python seed_from_images.py
"""

import base64
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent / ".env")

IMAGE_DIR   = Path(r"C:\Users\Asus\Desktop\archive\X")
BATCH_DELAY = 5   # seconds between Gemini calls — stays within free-tier 15 RPM
MAX_IMAGES  = 121

_VISION_PROMPT = (
    "You are analysing a residential floor plan image for a Sri Lankan architectural "
    "planning AI system. Describe this floor plan in 4-6 sentences covering:\n"
    "1. Number of floors visible and the overall layout style (open-plan, corridor-based, etc.)\n"
    "2. Room types present (living room, bedrooms, kitchen, bathrooms, dining, verandah, etc.) "
    "and their approximate relative sizes and positions\n"
    "3. Key adjacencies — which rooms are next to each other\n"
    "4. Staircase position and circulation path if visible\n"
    "5. Any notable features such as balcony, verandah, garage, or courtyard\n\n"
    "Write as a single descriptive paragraph suitable for retrieving similar floor plans in a "
    "Sri Lankan residential context. Do not use bullet points."
)


def main() -> None:
    try:
        import google.generativeai as genai
        from sentence_transformers import SentenceTransformer
        from supabase import create_client
    except ImportError as exc:
        print(f"Missing package: {exc}\nRun: pip install google-generativeai sentence-transformers supabase")
        sys.exit(1)

    api_key      = os.getenv("GEMINI_API_KEY", "")
    supabase_url = os.getenv("SUPABASE_URL", "")
    supabase_key = os.getenv("SUPABASE_KEY", "")

    if not all([api_key, supabase_url, supabase_key]):
        print("Missing GEMINI_API_KEY / SUPABASE_URL / SUPABASE_KEY in .env")
        sys.exit(1)

    if not IMAGE_DIR.exists():
        print(f"Image folder not found: {IMAGE_DIR}")
        sys.exit(1)

    genai.configure(api_key=api_key)
    model    = genai.GenerativeModel("gemini-2.5-flash")
    embedder = SentenceTransformer("all-MiniLM-L6-v2")
    client   = create_client(supabase_url, supabase_key)

    # Fetch already-processed filenames to allow resume
    existing  = client.table("sl_residential_plans").select("metadata").execute()
    processed = {
        row["metadata"]["source_file"]
        for row in (existing.data or [])
        if (row.get("metadata") or {}).get("source_file")
    }
    print(f"Already in Supabase : {len(existing.data or [])} entries")
    print(f"Already processed   : {len(processed)} image files\n")

    images   = sorted(IMAGE_DIR.glob("*.png"))[:MAX_IMAGES]
    todo     = [img for img in images if img.name not in processed]
    print(f"Images found : {len(images)}")
    print(f"To process   : {len(todo)}")
    print(f"Estimated time: ~{len(todo) * BATCH_DELAY // 60} min {len(todo) * BATCH_DELAY % 60} sec\n")

    inserted = skipped = failed = 0

    for i, img_path in enumerate(todo, 1):
        print(f"[{i}/{len(todo)}] {img_path.name} ...", end=" ", flush=True)

        try:
            img_b64 = base64.b64encode(img_path.read_bytes()).decode("utf-8")

            response = model.generate_content(
                [_VISION_PROMPT, {"mime_type": "image/png", "data": img_b64}],
                generation_config=genai.GenerationConfig(
                    temperature=0.3,
                    max_output_tokens=512,
                ),
            )
            description = response.text.strip()

            if len(description) < 40:
                print("⚠ description too short, skipping")
                failed += 1
                time.sleep(2)
                continue

            embedding = embedder.encode([description]).tolist()[0]

            client.table("sl_residential_plans").insert({
                "content":   description,
                "embedding": embedding,
                "metadata": {
                    "source":      "cvc_fpp_dataset",
                    "source_file": img_path.name,
                    "style":       "residential",
                    "context":     "sri_lankan_residential",
                },
            }).execute()

            inserted += 1
            print(f"✓  {description[:90]}...")

        except Exception as exc:
            print(f"✗ {exc}")
            failed += 1
            time.sleep(3)
            continue

        time.sleep(BATCH_DELAY)

    print(f"\n{'='*60}")
    print(f"Inserted : {inserted}")
    print(f"Skipped  : {skipped}")
    print(f"Failed   : {failed}")
    total = len(existing.data or []) + inserted
    print(f"Total RAG entries in Supabase now: ~{total}")


if __name__ == "__main__":
    main()
