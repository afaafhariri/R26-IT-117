"""Knowledge base ingestor — loads design precedent documents into ChromaDB."""

import os
from pathlib import Path

from utils.logger import get_logger
from knowledge_base.embedder import DocumentEmbedder

_logger = get_logger("ingest")

_DEFAULT_NORMS: list[str] = [
    (
        "Sri Lankan residential buildings typically have the living room facing the road "
        "for visual connection to street activity. The entrance porch (verandah) acts as "
        "a transitional buffer between public and private zones, common in both urban "
        "and rural housing."
    ),
    (
        "Kitchen and dining rooms are adjacent in Sri Lankan residential design to allow "
        "easy serving. The kitchen is typically at the rear of the house to contain "
        "cooking odours and is connected to a back yard for washing and utility purposes."
    ),
    (
        "Cross-ventilation is essential in Sri Lanka's tropical climate (average humidity "
        "75-85%). Buildings should have openings on at least two opposing walls to capture "
        "prevailing southwest monsoon winds. Corridor spaces can act as wind channels. "
        "Roof pitch of 30-45 degrees promotes stack-effect ventilation."
    ),
    (
        "Master bedrooms are typically placed away from road noise in Sri Lankan residential "
        "design, usually at the rear or upper floors. Privacy from the street is considered "
        "more important than view. Attached bathrooms are standard in medium and luxury tier."
    ),
    (
        "Bathrooms should not face the main entrance in Sri Lankan tradition. They are "
        "typically placed at the rear or sides of the house. Ventilation shafts or "
        "clerestory windows are used for natural light and airflow in internal bathrooms."
    ),
]


class KnowledgeBaseIngestor:
    """Ingests design precedent documents into ChromaDB for RAG retrieval.

    Run manually when new design documents are added to knowledge_base/corpus/.
    Supported formats: .txt, .md (text-based floor plan descriptions).
    """

    def __init__(self) -> None:
        import chromadb

        chroma_host = os.getenv("CHROMA_HOST", "localhost")
        chroma_port = int(os.getenv("CHROMA_PORT", "8000"))
        self.client = chromadb.HttpClient(host=chroma_host, port=chroma_port)
        self.embedder = DocumentEmbedder()
        self.corpus_dir = Path(os.getenv("CORPUS_DIR", "/app/knowledge_base/corpus"))
        self.collection_name = "sl_residential_plans"
        self.collection = self._get_or_create_collection()
        _logger.info("KnowledgeBaseIngestor ready — corpus_dir=%s", self.corpus_dir)

    def _get_or_create_collection(self):
        """Returns the ChromaDB collection, creating it if absent."""
        try:
            return self.client.get_collection(self.collection_name)
        except Exception:
            _logger.info("Creating collection '%s'", self.collection_name)
            return self.client.create_collection(
                self.collection_name,
                metadata={"hnsw:space": "cosine"},
            )

    def _chunk_text(self, text: str, max_chars: int = 500, overlap: int = 50) -> list[str]:
        """Splits text into overlapping chunks on paragraph boundaries.

        Args:
            text: Full document text.
            max_chars: Maximum characters per chunk.
            overlap: Character overlap between consecutive chunks.

        Returns:
            list[str]: List of text chunks.
        """
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        chunks: list[str] = []
        current = ""
        for para in paragraphs:
            if len(current) + len(para) + 2 <= max_chars:
                current = (current + "\n\n" + para).strip()
            else:
                if current:
                    chunks.append(current)
                current = para[-overlap:] + "\n\n" + para if overlap else para
        if current:
            chunks.append(current)
        return chunks

    def ingest_all(self) -> dict:
        """Reads all .txt and .md files from corpus_dir and upserts into ChromaDB.

        Skips files already ingested (by filename-based chunk ID prefix).

        Returns:
            dict: {ingested: int, skipped: int, errors: int}
        """
        if not self.corpus_dir.exists():
            _logger.warning("Corpus directory not found: %s", self.corpus_dir)
            return {"ingested": 0, "skipped": 0, "errors": 0}

        files = list(self.corpus_dir.glob("*.txt")) + list(self.corpus_dir.glob("*.md"))
        ingested = skipped = errors = 0

        existing_ids: set[str] = set()
        try:
            existing = self.collection.get()
            existing_ids = set(existing.get("ids", []))
        except Exception:
            pass

        for file_path in files:
            try:
                text = file_path.read_text(encoding="utf-8")
                chunks = self._chunk_text(text)
                new_ids: list[str] = []
                new_docs: list[str] = []

                for idx, chunk in enumerate(chunks):
                    chunk_id = f"{file_path.stem}_chunk_{idx}"
                    if chunk_id in existing_ids:
                        skipped += 1
                        continue
                    new_ids.append(chunk_id)
                    new_docs.append(chunk)

                if new_docs:
                    vectors = self.embedder.embed(new_docs)
                    self.collection.upsert(
                        ids=new_ids,
                        documents=new_docs,
                        embeddings=vectors,
                    )
                    ingested += len(new_docs)
                    _logger.info(
                        "Ingested %d chunks from %s", len(new_docs), file_path.name
                    )

            except Exception as exc:
                _logger.error("Failed to ingest %s: %s", file_path, exc)
                errors += 1

        # TODO Sprint 5: add PDF text extraction for design guides
        _logger.info(
            "Ingestion complete — ingested=%d, skipped=%d, errors=%d",
            ingested,
            skipped,
            errors,
        )
        return {"ingested": ingested, "skipped": skipped, "errors": errors}

    def add_default_design_norms(self) -> None:
        """Seeds the knowledge base with hardcoded Sri Lankan design norms.

        Ensures RAG always has at least some context even before real data
        is collected. Safe to call multiple times — uses stable IDs.
        """
        ids = [f"default_norm_{i}" for i in range(len(_DEFAULT_NORMS))]
        vectors = self.embedder.embed(_DEFAULT_NORMS)
        self.collection.upsert(
            ids=ids,
            documents=_DEFAULT_NORMS,
            embeddings=vectors,
        )
        _logger.info(
            "Seeded %d default design norms into '%s'",
            len(_DEFAULT_NORMS),
            self.collection_name,
        )
