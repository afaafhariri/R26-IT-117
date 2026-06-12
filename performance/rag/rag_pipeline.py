"""
RAG Pipeline — called after ML prediction to retrieve similar delay cases.

Usage:
    from rag.rag_pipeline import retrieve_similar_cases

    cases = retrieve_similar_cases(
        phase_group  = "Foundations",
        sub_phase    = "Foundation work",
        district     = "Vavuniya",
        province     = "Northern Province",
        delay_risk   = "MEDIUM",
        delay_days   = 46,
        top_k        = 3
    )
"""

from rag.embedder    import embed_texts
from rag.faiss_index import search


def _build_query(
    phase_group : str,
    sub_phase   : str,
    district    : str,
    province    : str,
    delay_risk  : str,
    delay_days  : int,
) -> str:
    """
    Build a natural-language query string that represents
    the current project context for similarity search.
    """
    return (
        f"Construction delay in {phase_group} / {sub_phase} phase "
        f"located in {district}, {province}. "
        f"Predicted risk level is {delay_risk} "
        f"with an estimated delay of {delay_days} days."
    )


def retrieve_similar_cases(
    phase_group : str,
    sub_phase   : str,
    district    : str,
    province    : str,
    delay_risk  : str,
    delay_days  : int,
    top_k       : int = 3,
) -> list[dict]:
    """
    Embed the current project context and search the FAISS index
    for the top-k most similar historical delay cases.

    Returns:
        list of dicts:
        [
          {
            "rank"    : 1,
            "case"    : "case_0042.txt",
            "summary" : "Case 42: ...(first 300 chars)...",
            "score"   : 0.1234,
          },
          ...
        ]
    """
    query       = _build_query(phase_group, sub_phase, district, province, delay_risk, delay_days)
    embedding   = embed_texts([query])                 # shape (1, 384)
    raw_results = search(embedding, top_k=top_k)

    results = []
    for r in raw_results:
        results.append({
            "rank"    : r["rank"],
            "case"    : r["filename"],
            "summary" : r["text"][:400].strip() + "...",
            "score"   : r["score"],
        })

    return results
