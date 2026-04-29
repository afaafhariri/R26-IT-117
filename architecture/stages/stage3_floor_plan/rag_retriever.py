"""
rag_retriever.py — ChromaDB-backed RAG retriever for floor plan examples.

Queries the knowledge base for similar Sri Lankan residential floor plans
to provide context to the LLM prompt.
"""

import os
import logging
from typing import Any

logger = logging.getLogger(__name__)

_CHROMA_COLLECTION = "floor_plans"
_TOP_K = 3


class RAGRetriever:
    """
    Retrieves semantically similar floor plan examples from ChromaDB
    to augment the LLM generation prompt.
    """

    def __init__(self) -> None:
        self._client = self._init_chroma()
        self._collection = self._get_collection()

    def _init_chroma(self) -> Any:
        """Initialise ChromaDB persistent client."""
        try:
            import chromadb  # type: ignore

            persist_dir = os.getenv("CHROMA_PERSIST_DIR", "/tmp/chroma")
            return chromadb.PersistentClient(path=persist_dir)
        except ImportError:
            logger.warning("ChromaDB not available — RAG retrieval will use stubs.")
            return None

    def _get_collection(self) -> Any:
        """Return or create the floor_plans collection."""
        if self._client is None:
            return None
        try:
            return self._client.get_or_create_collection(name=_CHROMA_COLLECTION)
        except Exception as exc:
            logger.warning("Could not access ChromaDB collection: %s", exc)
            return None

    def retrieve(self, buildable_zone: dict, user_requirements: dict) -> list[dict]:
        """
        Retrieve the top-K most similar floor plan examples from the vector store.

        Args:
            buildable_zone:    Buildable Zone JSON from Stage 2.
            user_requirements: User-supplied room list, finish grade, style, etc.

        Returns:
            List of up to K dicts: {"metadata": {...}, "document": str}
        """
        query = self._build_query_string(buildable_zone, user_requirements)

        if self._collection is None:
            logger.warning("No ChromaDB collection — returning stub RAG results.")
            return self._stub_results()

        try:
            results = self._collection.query(
                query_texts=[query],
                n_results=_TOP_K,
                include=["metadatas", "documents"],
            )
            retrieved = []
            for meta, doc in zip(
                results.get("metadatas", [[]])[0],
                results.get("documents", [[]])[0],
            ):
                retrieved.append({"metadata": meta, "document": doc})
            return retrieved

        except Exception as exc:
            logger.exception("ChromaDB query failed: %s", exc)
            return self._stub_results()

    @staticmethod
    def _build_query_string(buildable_zone: dict, user_requirements: dict) -> str:
        """
        Construct a natural-language query from site and requirement data.
        TODO: experiment with structured query templates for better recall.
        """
        area = buildable_zone.get("buildable_area_sqm", "unknown")
        floors = buildable_zone.get("recommended_floors", 2)
        rooms = user_requirements.get("rooms", [])
        style = user_requirements.get("style", "modern")
        return (
            f"Sri Lankan residential floor plan, {floors} floors, "
            f"{area} sqm buildable area, {style} style, rooms: {', '.join(rooms)}"
        )

    @staticmethod
    def _stub_results() -> list[dict]:
        """Placeholder RAG results for development without ChromaDB."""
        # TODO: replace with real vector store queries
        return [
            {
                "metadata": {
                    "plan_id": "stub_001",
                    "style": "modern",
                    "floors": 2,
                    "area_sqm": 150,
                },
                "document": (
                    "3-bedroom, 2-bathroom modern Sri Lankan house. "
                    "Open-plan living/dining, covered veranda at front, "
                    "laundry adjacent to kitchen. Master bedroom with en-suite."
                ),
            }
        ]
