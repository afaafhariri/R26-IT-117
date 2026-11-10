"""Supabase pgvector-backed RAG retriever for Sri Lankan residential floor plan precedents."""

import os

from utils.logger import get_logger

_logger = get_logger("rag_retriever")

_FALLBACK_NORMS = [
    (
        "Sri Lankan residential buildings typically have the living room facing the road "
        "for visual connection to street activity. The entrance porch (verandah) acts as "
        "a transitional buffer between public and private zones."
    ),
    (
        "Kitchen and dining rooms are adjacent in Sri Lankan residential design to allow "
        "easy serving. The kitchen is typically at the rear of the house to contain cooking "
        "odours and is connected to a back yard for washing and utility purposes."
    ),
    (
        "Cross-ventilation is essential in Sri Lanka's tropical climate. Buildings should "
        "have openings on at least two opposing walls to capture prevailing southwest monsoon "
        "winds. Corridor spaces can act as wind channels. Roof pitch of 30–45° promotes "
        "stack-effect ventilation."
    ),
]


class RAGRetriever:
    """Retrieves semantically relevant Sri Lankan residential floor plan precedents
    and design norms from Supabase pgvector to ground LLM generation.
    """

    def __init__(self) -> None:
        from sentence_transformers import SentenceTransformer

        self.client = None
        self.table = "sl_residential_plans"

        supabase_url = os.getenv("SUPABASE_URL", "")
        supabase_key = os.getenv("SUPABASE_KEY", "")

        if supabase_url and supabase_key:
            try:
                from supabase import create_client
                self.client = create_client(supabase_url, supabase_key)
                _logger.info("Connected to Supabase pgvector, table=%s", self.table)
            except ImportError:
                _logger.warning("supabase package not installed — RAG will use fallback norms")
            except Exception as exc:
                _logger.warning(
                    "Supabase connection failed (%s) — RAG will use fallback norms", exc
                )
        else:
            _logger.warning("SUPABASE_URL/KEY not set — RAG will use fallback norms")

        self.embedder = SentenceTransformer("all-MiniLM-L6-v2")
        _logger.info("RAGRetriever initialised")

    def retrieve(
        self,
        buildable_zone: dict,
        user_requirements: dict,
        top_k: int = 5,
    ) -> list[str]:
        """Retrieves top-k relevant design precedents for the given site.

        Args:
            buildable_zone: Output dict from Stage 2 BuildableZoneCalculator.
            user_requirements: User form input dict.
            top_k: Number of precedents to retrieve.

        Returns:
            list[str]: Text passages describing relevant floor plan precedents.
                Falls back to hardcoded design norms if Supabase is not configured
                or the table is empty.
        """
        room_types = ", ".join(user_requirements.get("room_types", []))
        style = user_requirements.get("style", "modern")
        footprint = buildable_zone.get("max_footprint_sqm", 0)
        floors = user_requirements.get("floors", 1)

        query = (
            f"Sri Lankan residential {style} house with {room_types}, "
            f"{floors} floor(s), footprint approximately {footprint:.0f} sqm"
        )

        if self.client is None:
            _logger.warning("No Supabase client — returning fallback design norms")
            return list(_FALLBACK_NORMS)

        try:
            query_vector = self.embedder.encode([query]).tolist()[0]
            response = self.client.rpc(
                "match_sl_plans",
                {"query_embedding": query_vector, "match_count": top_k},
            ).execute()

            passages = [row["content"] for row in (response.data or [])]

            if not passages:
                _logger.warning("Supabase table empty — returning fallback design norms")
                return list(_FALLBACK_NORMS)

            _logger.info(
                "RAG retrieved %d passages (footprint=%.0f, style=%s)",
                len(passages),
                footprint,
                style,
            )
            return passages

        except Exception as exc:
            _logger.warning("Supabase query failed (%s) — returning fallback norms", exc)
            return list(_FALLBACK_NORMS)
