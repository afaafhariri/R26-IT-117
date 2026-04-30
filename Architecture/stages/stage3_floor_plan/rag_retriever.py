"""ChromaDB-backed RAG retriever for Sri Lankan residential floor plan precedents."""

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
    and design norms from ChromaDB to ground LLM generation.
    """

    def __init__(self) -> None:
        import chromadb
        from sentence_transformers import SentenceTransformer

        chroma_host = os.getenv("CHROMA_HOST", "localhost")
        chroma_port = int(os.getenv("CHROMA_PORT", "8000"))
        self.collection_name = "sl_residential_plans"

        try:
            self.client = chromadb.HttpClient(host=chroma_host, port=chroma_port)
            self.collection = self._get_or_create_collection()
            _logger.info(
                "Connected to ChromaDB at %s:%s, collection=%s",
                chroma_host,
                chroma_port,
                self.collection_name,
            )
        except Exception as exc:
            _logger.warning(
                "ChromaDB connection failed (%s) — RAG will use fallback norms", exc
            )
            self.client = None
            self.collection = None

        self.embedder = SentenceTransformer("all-MiniLM-L6-v2")
        _logger.info("RAGRetriever initialised")

    def _get_or_create_collection(self):
        """Returns the ChromaDB collection, creating it if absent."""
        try:
            return self.client.get_collection(self.collection_name)
        except Exception:
            _logger.warning(
                "Collection '%s' not found — creating empty collection",
                self.collection_name,
            )
            return self.client.create_collection(
                self.collection_name,
                metadata={"hnsw:space": "cosine"},
            )

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
                Falls back to hardcoded design norms if collection is empty.
        """
        room_types = ", ".join(user_requirements.get("room_types", []))
        style = user_requirements.get("style", "modern")
        footprint = buildable_zone.get("max_footprint_sqm", 0)
        floors = user_requirements.get("floors", 1)

        query = (
            f"Sri Lankan residential {style} house with {room_types}, "
            f"{floors} floor(s), footprint approximately {footprint:.0f} sqm"
        )

        if self.collection is None:
            _logger.warning("No ChromaDB collection — returning fallback design norms")
            return list(_FALLBACK_NORMS)

        try:
            count = self.collection.count()
        except Exception:
            count = 0

        if count == 0:
            _logger.warning(
                "Collection '%s' is empty — returning fallback design norms",
                self.collection_name,
            )
            return list(_FALLBACK_NORMS)

        query_vector = self.embedder.encode([query]).tolist()[0]
        results = self.collection.query(
            query_embeddings=[query_vector],
            n_results=min(top_k, count),
        )

        passages = results.get("documents", [[]])[0]
        _logger.info(
            "RAG retrieved %d passages for query (footprint=%.0f, style=%s)",
            len(passages),
            footprint,
            style,
        )
        return passages if passages else list(_FALLBACK_NORMS)
