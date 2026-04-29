"""
ingest.py — Ingests floor plan reference documents into the ChromaDB vector store.

Run this script once (or on update) to populate the knowledge base
from a directory of text/JSON floor plan descriptions.

Usage:
    python -m knowledge_base.ingest --docs-dir /path/to/documents
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

from knowledge_base.embedder import DocumentEmbedder

logger = logging.getLogger(__name__)

_CHROMA_COLLECTION = "floor_plans"
_SUPPORTED_EXTENSIONS = {".txt", ".json", ".md"}


class KnowledgeBaseIngestor:
    """Loads floor plan documents and upserts them into ChromaDB."""

    def __init__(self) -> None:
        self._embedder = DocumentEmbedder()
        self._collection = self._init_collection()

    def _init_collection(self) -> Any:
        """Initialise the ChromaDB collection."""
        try:
            import chromadb  # type: ignore

            persist_dir = os.getenv("CHROMA_PERSIST_DIR", "/tmp/chroma")
            client = chromadb.PersistentClient(path=persist_dir)
            return client.get_or_create_collection(name=_CHROMA_COLLECTION)
        except ImportError:
            logger.error("ChromaDB not installed — cannot ingest documents.")
            return None

    def ingest_directory(self, docs_dir: Path) -> int:
        """
        Load all supported documents from a directory and upsert into ChromaDB.

        Args:
            docs_dir: Path to directory containing floor plan documents.

        Returns:
            Number of documents successfully ingested.

        Raises:
            FileNotFoundError: If docs_dir does not exist.
        """
        if not docs_dir.exists():
            raise FileNotFoundError(f"Documents directory not found: {docs_dir}")

        doc_files = [
            f for f in docs_dir.iterdir()
            if f.is_file() and f.suffix.lower() in _SUPPORTED_EXTENSIONS
        ]

        if not doc_files:
            logger.warning("No supported documents found in %s", docs_dir)
            return 0

        ingested = 0
        for doc_path in doc_files:
            try:
                text, metadata = self._load_document(doc_path)
                self._upsert(doc_id=doc_path.stem, text=text, metadata=metadata)
                ingested += 1
                logger.info("Ingested: %s", doc_path.name)
            except Exception as exc:
                logger.error("Failed to ingest %s: %s", doc_path.name, exc)

        logger.info("Ingestion complete: %d / %d documents", ingested, len(doc_files))
        return ingested

    def _load_document(self, path: Path) -> tuple[str, dict]:
        """
        Read a document file and extract text + metadata.
        JSON files are expected to have 'description' and optional 'metadata' keys.
        """
        if path.suffix.lower() == ".json":
            data = json.loads(path.read_text(encoding="utf-8"))
            text = data.get("description", json.dumps(data))
            metadata = data.get("metadata", {"source": path.name})
        else:
            text = path.read_text(encoding="utf-8")
            metadata = {"source": path.name}

        # Ensure metadata values are all strings (ChromaDB requirement)
        metadata = {k: str(v) for k, v in metadata.items()}
        return text, metadata

    def _upsert(self, doc_id: str, text: str, metadata: dict) -> None:
        """Embed and upsert a single document into ChromaDB."""
        if self._collection is None:
            logger.warning("ChromaDB unavailable — skipping upsert for %s", doc_id)
            return

        embedding = self._embedder.embed_single(text)
        self._collection.upsert(
            ids=[doc_id],
            documents=[text],
            embeddings=[embedding],
            metadatas=[metadata],
        )


# ── CLI entry point ───────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest floor plan documents into the ChromaDB knowledge base."
    )
    parser.add_argument(
        "--docs-dir",
        type=Path,
        default=Path("knowledge_base/documents"),
        help="Directory containing floor plan reference documents.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    args = _parse_args()
    ingestor = KnowledgeBaseIngestor()
    count = ingestor.ingest_directory(args.docs_dir)
    print(f"Ingested {count} documents.")
    sys.exit(0 if count >= 0 else 1)
