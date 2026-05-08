import os
import csv
from sentence_transformers import SentenceTransformer

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Primary path: local data/ copy (works in Docker and locally)
# Fallback: research/ path (works locally when running outside Docker)
_LOCAL_CSV    = os.path.join(BASE_DIR, "data", "delay_data.csv")
_RESEARCH_CSV = os.path.join(BASE_DIR, "..", "research", "datasets", "delay-cases", "delay_data.csv")
CSV_PATH      = _LOCAL_CSV if os.path.exists(_LOCAL_CSV) else _RESEARCH_CSV
RAG_CASES_DIR = os.path.join(BASE_DIR, "data", "rag_cases")

# ── Model ─────────────────────────────────────────────────────────────────────
MODEL_NAME = "all-MiniLM-L6-v2"
_model     = None


def get_model():
    global _model
    if _model is None:
        print(f"[embedder] Loading SentenceTransformer: {MODEL_NAME}")
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def embed_texts(texts: list[str]):
    """Convert a list of strings to numpy embeddings."""
    model = get_model()
    return model.encode(texts, show_progress_bar=False, convert_to_numpy=True)


# ── Story generation ──────────────────────────────────────────────────────────

def _row_to_story(row: dict, case_id: int) -> str:
    """Convert one CSV row into a natural-language story."""
    risk      = row.get("delay_risk", "").upper()
    days      = row.get("delay_days", "unknown")
    cause     = row.get("cause_of_delay", "").strip()
    action    = row.get("corrective_action_taken", "").strip()
    status    = row.get("construction_status", "").strip()
    category  = row.get("delay_category", "").strip()
    province  = row.get("province", "").strip()
    district  = row.get("district", "").strip()
    floors    = row.get("floors", "")
    phase_grp = row.get("phase_group", "").strip()
    sub_phase = row.get("sub_phase", "").strip()
    labour    = row.get("labour_availability", "")
    material  = "available" if str(row.get("material_supply", "1")) == "1" else "unavailable"
    weather   = row.get("weather_severity", "")
    cum_delay = row.get("cumulative_delay", "")

    story = f"""Case {case_id}: Construction Delay - {phase_grp} / {sub_phase}

Location   : {district}, {province}
Building   : {floors}-floor residential construction
Phase      : {phase_grp} > {sub_phase}
Risk Level : {risk}
Delay Days : {days} days

Delay Category : {category}
Cause of Delay : {cause}

Site Conditions:
  - Labour availability  : {labour}
  - Material supply      : {material}
  - Weather severity     : {weather}
  - Cumulative delay so far: {cum_delay} days

Corrective Action Taken:
  {action}

Construction Status:
  {status}
"""
    return story.strip()


def generate_rag_documents():
    """
    Read delay_data.csv and write one .txt story file per row
    into performance/data/rag_cases/.
    Returns the number of files written.
    """
    os.makedirs(RAG_CASES_DIR, exist_ok=True)

    csv_path = os.path.abspath(CSV_PATH)
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    written = 0
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for idx, row in enumerate(reader, start=1):
            story    = _row_to_story(row, idx)
            filename = f"case_{idx:04d}.txt"
            filepath = os.path.join(RAG_CASES_DIR, filename)
            with open(filepath, "w", encoding="utf-8") as out:
                out.write(story)
            written += 1

    print(f"[embedder] {written} story documents written to {RAG_CASES_DIR}")
    return written
