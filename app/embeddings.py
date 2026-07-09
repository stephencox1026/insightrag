"""Embedding providers.

Two implementations behind one interface:

- OpenAIEmbeddings: real semantic embeddings (requires OPENAI_API_KEY).
- HashingEmbeddings: deterministic, dependency-free feature-hashing embeddings
  used in OFFLINE mode. Retrieval quality is lexical rather than semantic, but
  it keeps the whole pipeline runnable (and tests deterministic) with no key.

The offline path pairs with BM25 in the hybrid retriever, so lexical recall
stays reasonable for demos even without a model.
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol

import numpy as np

from .config import Settings

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


class Embeddings(Protocol):
    dim: int

    def embed(self, texts: list[str]) -> np.ndarray:  # (n, dim) float32, L2-normed
        ...


class HashingEmbeddings:
    """Feature-hashing embeddings: deterministic and offline.

    Each token is hashed into a fixed-dimension vector with a signed value,
    then the document vector is L2-normalized. Cosine similarity over these
    vectors approximates weighted lexical overlap.
    """

    def __init__(self, dim: int = 512) -> None:
        self.dim = dim

    def _embed_one(self, text: str) -> np.ndarray:
        vec = np.zeros(self.dim, dtype=np.float32)
        tokens = _tokenize(text)
        if not tokens:
            return vec
        for tok in tokens:
            h = hashlib.md5(tok.encode("utf-8")).digest()
            idx = int.from_bytes(h[:4], "little") % self.dim
            sign = 1.0 if h[4] & 1 else -1.0
            vec[idx] += sign
        norm = float(np.linalg.norm(vec))
        if norm > 0:
            vec /= norm
        return vec

    def embed(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        return np.vstack([self._embed_one(t) for t in texts])


class OpenAIEmbeddings:
    def __init__(self, api_key: str, model: str) -> None:
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key)
        self._model = model
        # Dimensions for text-embedding-3-small; overwritten after first call.
        self.dim = 1536

    def embed(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        # OpenAI recommends batching; keep batches modest for token limits.
        vectors: list[list[float]] = []
        batch_size = 128
        for start in range(0, len(texts), batch_size):
            batch = texts[start : start + batch_size]
            resp = self._client.embeddings.create(model=self._model, input=batch)
            vectors.extend([d.embedding for d in resp.data])
        arr = np.array(vectors, dtype=np.float32)
        self.dim = arr.shape[1]
        # L2 normalize so dot product == cosine similarity.
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return arr / norms


def get_embeddings(settings: Settings, *, offline: bool | None = None) -> Embeddings:
    use_offline = settings.is_offline if offline is None else offline
    if use_offline:
        return HashingEmbeddings()
    return OpenAIEmbeddings(api_key=settings.openai_api_key, model=settings.embed_model)


def cosine_scores(query_vec: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    """Cosine similarity of a single (dim,) query against a (n, dim) matrix.

    Assumes rows are L2-normalized (our providers guarantee this)."""
    if matrix.shape[0] == 0:
        return np.zeros(0, dtype=np.float32)
    q = query_vec
    qn = float(np.linalg.norm(q))
    if qn > 0:
        q = q / qn
    return matrix @ q


def softmax(xs: list[float]) -> list[float]:
    if not xs:
        return []
    m = max(xs)
    exps = [math.exp(x - m) for x in xs]
    total = sum(exps) or 1.0
    return [e / total for e in exps]
