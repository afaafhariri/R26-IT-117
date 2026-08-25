import os
import json
import faiss
import numpy as np

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAG_CASES_DIR = os.path.join(BASE_DIR, "data", "rag_cases")
MODELS_DIR    = os.path.join(BASE_DIR, "models")
INDEX_PATH    = os.path.join(MODELS_DIR, "faiss_rag.index")
META_PATH     = os.path.join(MODELS_DIR, "faiss_rag_meta.json")

# ── Lazy globals ──────────────────────────────────────────────────────────────
_index    = None
_metadata = None   # list of {"filename": ..., "text": ...}


def build_index():
    """
    Load all .txt files from data/rag_cases/,
    embed them, build a FAISS flat-L2 index,
    and save index + metadata to models/.
    """
    from rag.embedder import embed_texts

    txt_files = sorted([
        f for f in os.listdir(RAG_CASES_DIR) if f.endswith(".txt")
    ])

    if not txt_files:
        raise FileNotFoundError(
            f"No .txt files found in {RAG_CASES_DIR}. "
            "Run generate_rag_documents() first."
        )

    print(f"[faiss_index] Loading {len(txt_files)} story documents...")
    texts     = []
    meta      = []

    for fname in txt_files:
        fpath = os.path.join(RAG_CASES_DIR, fname)
        with open(fpath, "r", encoding="utf-8") as f:
            text = f.read()
        texts.append(text)
        meta.append({"filename": fname, "text": text})

    print(f"[faiss_index] Generating embeddings...")
    embeddings = embed_texts(texts)                  # (N, 384)
    embeddings = embeddings.astype(np.float32)

    dimension = embeddings.shape[1]
    index     = faiss.IndexFlatL2(dimension)
    index.add(embeddings)

    os.makedirs(MODELS_DIR, exist_ok=True)
    faiss.write_index(index, INDEX_PATH)

    with open(META_PATH, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    print(f"[faiss_index] FAISS index saved  : {INDEX_PATH}")
    print(f"[faiss_index] Metadata saved     : {META_PATH}")
    print(f"[faiss_index] Total vectors       : {index.ntotal}")
    return index.ntotal


def load_index():
    """Lazy-load the FAISS index and metadata into memory."""
    global _index, _metadata

    if _index is None:
        if not os.path.exists(INDEX_PATH):
            raise FileNotFoundError(
                f"FAISS index not found at {INDEX_PATH}. "
                "Run build_index() first."
            )
        _index = faiss.read_index(INDEX_PATH)

        with open(META_PATH, "r", encoding="utf-8") as f:
            _metadata = json.load(f)

        print(f"[faiss_index] Index loaded — {_index.ntotal} vectors")

    return _index, _metadata


def search(query_embedding: np.ndarray, top_k: int = 3):
    """
    Search the FAISS index.

    Args:
        query_embedding : numpy array shape (1, 384) or (384,)
        top_k           : number of results to return

    Returns:
        list of dicts [{"rank": 1, "filename": ..., "text": ..., "score": ...}]
    """
    index, metadata = load_index()

    q = np.array(query_embedding, dtype=np.float32)
    if q.ndim == 1:
        q = q.reshape(1, -1)

    distances, indices = index.search(q, top_k)

    results = []
    for rank, (dist, idx) in enumerate(zip(distances[0], indices[0]), start=1):
        if idx == -1:
            continue
        results.append({
            "rank":     rank,
            "filename": metadata[idx]["filename"],
            "text":     metadata[idx]["text"],
            "score":    round(float(dist), 4),
        })

    return results
