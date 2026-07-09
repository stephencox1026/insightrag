"""Backward-compatible re-exports. Prefer app.vector_store."""

from .vector_store import (
    FileVectorIndex,
    PgVectorIndex,
    RetrievedChunk,
    VectorIndex,
    get_vector_index,
)

__all__ = ["FileVectorIndex", "PgVectorIndex", "RetrievedChunk", "VectorIndex", "get_vector_index"]
