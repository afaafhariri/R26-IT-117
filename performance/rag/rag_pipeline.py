from rag.embedder import embed_texts
from rag.faiss_index import search


def _build_query(district: str, phase_group: str, delay_category: str) -> str:
    return (
        f"Historical construction delays in {district} district for phase group {phase_group}. "
        f"Delay category focus: {delay_category}. "
        "Find similar Sri Lankan coastal residential cases with causes and corrective actions."
    )


def _extract_case_fields(text: str) -> dict:
    def _extract_after(prefix: str) -> str:
        for line in text.splitlines():
            if line.strip().startswith(prefix):
                return line.split(":", 1)[-1].strip()
        return ""

    cause = _extract_after("Cause of Delay")
    action = _extract_after("Corrective Action Taken")
    status = _extract_after("Construction Status")

    if not action:
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if line.strip().startswith("Corrective Action Taken"):
                if i + 1 < len(lines):
                    action = lines[i + 1].strip()
                break

    if not status:
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if line.strip().startswith("Construction Status"):
                if i + 1 < len(lines):
                    status = lines[i + 1].strip()
                break

    return {
        "cause_of_delay": cause,
        "corrective_action_taken": action,
        "construction_status": status,
    }


def retrieve_similar_cases(
    district: str,
    phase_group: str,
    delay_category: str,
    top_k: int = 3,
) -> list[dict]:
    query = _build_query(district, phase_group, delay_category)
    embedding = embed_texts([query])
    raw_results = search(embedding, top_k=top_k)

    results = []
    for r in raw_results:
        parsed = _extract_case_fields(r["text"])
        results.append(
            {
                "rank": r["rank"],
                "case": r["filename"],
                "score": r["score"],
                "cause_of_delay": parsed["cause_of_delay"],
                "corrective_action_taken": parsed["corrective_action_taken"],
                "construction_status": parsed["construction_status"],
                "summary": r["text"][:400].strip() + "...",
            }
        )
    return results
