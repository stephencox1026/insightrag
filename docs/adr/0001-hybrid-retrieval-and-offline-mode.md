# ADR 0001: Hybrid retrieval + offline-first design

## Status
Accepted (MVP)

## Context
The assistant must answer both conceptual document questions and concrete data
questions, be runnable by reviewers with zero setup, and produce metrics that
prove it works. Two decisions shaped the MVP.

## Decision 1: Hybrid retrieval (dense + BM25) over pure vector search
Pure dense retrieval misses exact-term matches (policy names, numbers, IDs);
pure BM25 misses paraphrases. We fuse both: cosine similarity over normalized
embeddings and BM25 keyword scores, each min-max normalized and combined with a
weight `HYBRID_ALPHA`.

**Consequences:** more robust recall on a small corpus; one extra dependency
(`rank-bm25`); BM25 is rebuilt in memory on load (cheap at MVP scale, revisit
for large corpora).

## Decision 2: Offline-first with a provider abstraction
Embeddings and LLM calls sit behind interfaces (`Embeddings`, `LLM`). When no
`OPENAI_API_KEY` is present, the app uses deterministic feature-hashing
embeddings and extractive answers.

**Why:** the demo never fails due to a missing key, rate limit, or outage;
tests are deterministic and free; reviewers can `make demo` immediately.

**Consequences:** offline answer quality is lower (extractive, lexical
retrieval), clearly labeled in the UI and metrics. Online mode uses real models
without code changes.

## Alternatives considered
- Dedicated vector DB (Chroma/pgvector): deferred. A numpy index behind a
  `VectorIndex` interface keeps the MVP dependency-light and swappable; pgvector
  lands in the production tier.
- Requiring an API key: rejected — it hurts reviewer experience and test
  reliability.
