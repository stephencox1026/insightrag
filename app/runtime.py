"""Runtime mode resolution — keep query-time embeddings aligned with the index."""

from __future__ import annotations

import json

from .config import Settings
from .db import connect

_HASHING_DIM = 512


def resolve_offline(settings: Settings, index_meta: dict, index_dim: int = 0) -> bool:
    """True when retrieval must use hashing embeddings.

    Ollama does not provide embeddings here, so retrieval stays on hashing/BM25.
    Generative SQL/answers are controlled separately by resolve_llm_offline().
    """
    if settings.offline or settings.uses_ollama:
        return True
    if not (settings.openai_api_key or "").strip():
        return True
    if index_meta.get("offline"):
        return True
    provider = index_meta.get("provider")
    if provider == "HashingEmbeddings":
        return True
    # Postgres reload may omit meta; infer from embedding width.
    if index_dim == _HASHING_DIM:
        return True
    return False


def resolve_llm_offline(settings: Settings) -> bool:
    """True when chat/SQL should avoid generative models (templates/extractive only)."""
    return settings.is_offline


def index_meta(settings: Settings) -> dict:
    """Lightweight index metadata for mode detection (no full Assistant load)."""
    if settings.uses_postgres:
        try:
            from .vector_store import _embedding_to_numpy

            with connect(settings) as conn:
                cur = conn.cursor()
                cur.execute("SELECT embedding FROM document_chunks LIMIT 1")
                row = cur.fetchone()
            if not row or row[0] is None:
                return {}
            dim = int(_embedding_to_numpy(row[0]).shape[0])
            offline = dim == _HASHING_DIM
            return {
                "dim": dim,
                "offline": offline,
                "provider": "HashingEmbeddings" if offline else "OpenAIEmbeddings",
            }
        except Exception:
            return {}
    meta_path = settings.index_dir / "meta.json"
    if meta_path.exists():
        try:
            return json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def effective_offline(settings: Settings) -> bool:
    meta = index_meta(settings)
    dim = int(meta.get("dim") or 0)
    return resolve_offline(settings, meta, dim)
