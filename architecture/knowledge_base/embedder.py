"""
embedder.py — Sentence-transformer document embedder for the floor plan knowledge base.

Converts floor plan text documents into dense vector embeddings
for storage in ChromaDB.
"""

import os
import logging
from typing import Any

logger = logging.getLogger(__name__)

_EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")


class DocumentEmbedder:
    """Wraps sentence-transformers to embed floor plan descriptions."""

    def __init__(self) -> None:
        self._model = self._load_model()

    def _load_model(self) -> Any:
        """Load the sentence-transformers model."""
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore

            logger.info("Loading embedding model: %s", _EMBEDDING_MODEL)
            return SentenceTransformer(_EMBEDDING_MODEL)
        except ImportError:
            logger.warning(
                "sentence-transformers not available — embedder in stub mode."
            )
            return None

    def embed(self, texts: list[str]) -> list[list[float]]:
        """
        Compute dense embeddings for a list of text documents.

        Args:
            texts: List of document strings to embed.

        Returns:
            List of embedding vectors (each a list of floats).

        Raises:
            RuntimeError: If embedding fails.
        """
        if not texts:
            return []

        if self._model is None:
            return self._stub_embeddings(texts)

        try:
            embeddings = self._model.encode(texts, convert_to_numpy=True)
            return [emb.tolist() for emb in embeddings]
        except Exception as exc:
            logger.exception("Embedding failed")
            raise RuntimeError(f"Embedding error: {exc}") from exc

    def embed_single(self, text: str) -> list[float]:
        """Convenience wrapper for embedding a single document."""
        return self.embed([text])[0]

    @staticmethod
    def _stub_embeddings(texts: list[str]) -> list[list[float]]:
        """Return zero vectors when the model is unavailable."""
        # TODO: replace with real embeddings in production
        return [[0.0] * 384 for _ in texts]
