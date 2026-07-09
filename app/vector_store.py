"""Vector index backends: file (numpy) or Postgres (pgvector).

Hybrid retrieval fuses dense cosine similarity with BM25 keyword scores.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
from rank_bm25 import BM25Okapi

from .chunking import Chunk
from .config import Settings
from .db import connect
from .embeddings import Embeddings, _tokenize, cosine_scores


@dataclass
class RetrievedChunk:
    chunk: Chunk
    score: float
    dense_score: float
    bm25_score: float


def _minmax(scores: np.ndarray) -> np.ndarray:
    if scores.size == 0:
        return scores
    lo, hi = float(scores.min()), float(scores.max())
    if hi - lo < 1e-9:
        return np.zeros_like(scores)
    return (scores - lo) / (hi - lo)


def _embedding_to_numpy(vec) -> np.ndarray:
    """Convert pgvector Vector, list, or ndarray to float32 numpy array."""
    if vec is None:
        return np.zeros(0, dtype=np.float32)
    if isinstance(vec, np.ndarray):
        return vec.astype(np.float32)
    if hasattr(vec, "to_list"):
        return np.array(vec.to_list(), dtype=np.float32)
    if hasattr(vec, "to_numpy"):
        return vec.to_numpy().astype(np.float32)
    return np.array(list(vec), dtype=np.float32)


class FileVectorIndex:
    def __init__(self, index_dir: Path) -> None:
        self.index_dir = Path(index_dir)
        self.chunks: list[Chunk] = []
        self.vectors: np.ndarray = np.zeros((0, 0), dtype=np.float32)
        self.meta: dict = {}
        self._bm25: BM25Okapi | None = None

    def build(self, chunks: list[Chunk], embeddings: Embeddings, offline: bool) -> None:
        self.chunks = chunks
        texts = [c.text for c in chunks]
        self.vectors = embeddings.embed(texts)
        self.meta = {
            "dim": int(self.vectors.shape[1]) if self.vectors.size else 0,
            "provider": type(embeddings).__name__,
            "offline": offline,
            "count": len(chunks),
            "backend": "file",
        }
        self._build_bm25()

    def save(self) -> None:
        self.index_dir.mkdir(parents=True, exist_ok=True)
        np.save(self.index_dir / "vectors.npy", self.vectors)
        with open(self.index_dir / "chunks.json", "w") as f:
            json.dump([asdict(c) for c in self.chunks], f)
        with open(self.index_dir / "meta.json", "w") as f:
            json.dump(self.meta, f, indent=2)

    def load(self) -> None:
        self.vectors = np.load(self.index_dir / "vectors.npy")
        with open(self.index_dir / "chunks.json") as f:
            self.chunks = [Chunk(**d) for d in json.load(f)]
        with open(self.index_dir / "meta.json") as f:
            self.meta = json.load(f)
        self._build_bm25()

    def exists(self) -> bool:
        return (self.index_dir / "vectors.npy").exists() and (
            self.index_dir / "chunks.json"
        ).exists()

    def _build_bm25(self) -> None:
        tokens = [_tokenize(c.text) for c in self.chunks]
        self._bm25 = BM25Okapi(tokens) if tokens else None

    def search(
        self, query: str, query_vec: np.ndarray, top_k: int = 5, alpha: float = 0.5
    ) -> list[RetrievedChunk]:
        if not self.chunks:
            return []
        dense_raw = cosine_scores(query_vec, self.vectors)
        bm25_raw = (
            np.array(self._bm25.get_scores(_tokenize(query)), dtype=np.float32)
            if self._bm25
            else np.zeros(len(self.chunks), dtype=np.float32)
        )
        return _fuse_and_rank(self.chunks, dense_raw, bm25_raw, top_k, alpha)


class PgVectorIndex:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.chunks: list[Chunk] = []
        self.vectors: np.ndarray = np.zeros((0, 0), dtype=np.float32)
        self.meta: dict = {"backend": "postgres"}

    def build(self, chunks: list[Chunk], embeddings: Embeddings, offline: bool) -> None:
        from pgvector.psycopg import register_vector

        texts = [c.text for c in chunks]
        vectors = embeddings.embed(texts)
        dim = int(vectors.shape[1]) if vectors.size else 512

        with connect(self.settings) as conn:
            register_vector(conn)
            cur = conn.cursor()
            cur.execute("DROP TABLE IF EXISTS document_chunks")
            cur.execute(
                f"""
                CREATE TABLE document_chunks (
                    id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    title TEXT NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    embedding vector({dim})
                )
                """
            )
            for chunk, vec in zip(chunks, vectors, strict=True):
                cur.execute(
                    """
                    INSERT INTO document_chunks (id, source, title, chunk_index, text, embedding)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (chunk.id, chunk.source, chunk.title, chunk.chunk_index, chunk.text, vec),
                )
            conn.commit()

        self.chunks = chunks
        self.vectors = vectors
        self.meta = {
            "dim": dim,
            "provider": type(embeddings).__name__,
            "offline": offline,
            "count": len(chunks),
            "backend": "postgres",
        }
        self._build_bm25()

    def save(self) -> None:
        pass  # persisted on build

    def load(self) -> None:
        from pgvector.psycopg import register_vector

        with connect(self.settings) as conn:
            register_vector(conn)
            cur = conn.cursor()
            cur.execute(
                "SELECT id, source, title, chunk_index, text, embedding "
                "FROM document_chunks ORDER BY id"
            )
            rows = cur.fetchall()
        self.chunks = [
            Chunk(id=r[0], source=r[1], title=r[2], chunk_index=r[3], text=r[4])
            for r in rows
        ]
        if rows and rows[0][5] is not None:
            self.vectors = np.vstack([_embedding_to_numpy(r[5]) for r in rows])
            dim = int(self.vectors.shape[1])
            self.meta["dim"] = dim
            if "offline" not in self.meta:
                self.meta["offline"] = dim == 512
            if "provider" not in self.meta:
                self.meta["provider"] = (
                    "HashingEmbeddings" if self.meta["offline"] else "OpenAIEmbeddings"
                )
        else:
            self.vectors = np.zeros((0, 0), dtype=np.float32)
        self.meta["count"] = len(self.chunks)
        self._build_bm25()

    def exists(self) -> bool:
        try:
            with connect(self.settings) as conn:
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM document_chunks")
                return cur.fetchone()[0] > 0
        except Exception:
            return False

    def _build_bm25(self) -> None:
        tokens = [_tokenize(c.text) for c in self.chunks]
        self._bm25 = BM25Okapi(tokens) if tokens else None

    def search(
        self, query: str, query_vec: np.ndarray, top_k: int = 5, alpha: float = 0.5
    ) -> list[RetrievedChunk]:
        if not self.chunks:
            return []
        dense_raw = cosine_scores(query_vec, self.vectors)
        bm25_raw = (
            np.array(self._bm25.get_scores(_tokenize(query)), dtype=np.float32)
            if self._bm25
            else np.zeros(len(self.chunks), dtype=np.float32)
        )
        return _fuse_and_rank(self.chunks, dense_raw, bm25_raw, top_k, alpha)


def _fuse_and_rank(
    chunks: list[Chunk],
    dense_raw: np.ndarray,
    bm25_raw: np.ndarray,
    top_k: int,
    alpha: float,
) -> list[RetrievedChunk]:
    dense_n = _minmax(dense_raw)
    bm25_n = _minmax(bm25_raw)
    fused = alpha * dense_n + (1 - alpha) * bm25_n
    top_idx = np.argsort(-fused)[:top_k]
    return [
        RetrievedChunk(
            chunk=chunks[int(i)],
            score=float(fused[int(i)]),
            dense_score=float(dense_raw[int(i)]),
            bm25_score=float(bm25_raw[int(i)]),
        )
        for i in top_idx
    ]


def get_vector_index(settings: Settings) -> FileVectorIndex | PgVectorIndex:
    if settings.uses_postgres:
        return PgVectorIndex(settings)
    return FileVectorIndex(settings.index_dir)


# Alias for imports that expect VectorIndex
VectorIndex = FileVectorIndex
