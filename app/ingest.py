"""Ingestion: read documents -> chunk -> embed -> persist index."""

from __future__ import annotations

from pathlib import Path

from .chunking import Chunk, chunk_text
from .config import Settings, get_settings
from .embeddings import get_embeddings
from .vector_store import get_vector_index


def _title_from(path: Path, text: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()
    return path.stem.replace("_", " ").title()


def load_documents(docs_dir: Path) -> list[Chunk]:
    settings = get_settings()
    chunks: list[Chunk] = []
    files = sorted([*docs_dir.glob("*.md"), *docs_dir.glob("*.txt")])
    for path in files:
        text = path.read_text(encoding="utf-8")
        title = _title_from(path, text)
        chunks.extend(
            chunk_text(
                text,
                source=path.name,
                title=title,
                chunk_size=settings.chunk_size,
                overlap=settings.chunk_overlap,
            )
        )
    return chunks


def build_index(settings: Settings | None = None) -> dict:
    settings = settings or get_settings()
    settings.ensure_dirs()
    docs_dir = Path(settings.data_dir) / "docs"
    chunks = load_documents(docs_dir)

    embeddings = get_embeddings(settings)
    index = get_vector_index(settings)
    index.build(chunks, embeddings, offline=settings.is_offline)
    index.save()

    return {
        "documents": len({c.source for c in chunks}),
        "chunks": len(chunks),
        "provider": index.meta.get("provider"),
        "dim": index.meta.get("dim"),
        "offline": settings.is_offline,
        "backend": index.meta.get("backend", settings.index_backend),
    }
