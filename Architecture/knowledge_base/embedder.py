"""Sentence-transformer document embedder for ChromaDB ingestion."""

from utils.logger import get_logger

_logger = get_logger("embedder")


class DocumentEmbedder:
    """Embeds text strings into dense vectors for ChromaDB storage and retrieval."""

    def __init__(self) -> None:
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer("all-MiniLM-L6-v2")
        _logger.info("DocumentEmbedder initialised (model=all-MiniLM-L6-v2)")

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embeds a list of text strings into vectors.

        Args:
            texts: List of document text strings to embed.

        Returns:
            list[list[float]]: List of embedding vectors matching input order.
        """
        vectors = self.model.encode(
            texts, batch_size=32, show_progress_bar=True
        ).tolist()
        _logger.info("Embedded %d documents", len(vectors))
        return vectors
