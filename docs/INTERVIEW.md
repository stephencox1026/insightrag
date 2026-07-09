# InsightRAG — Interview Talking Points

## 30-second pitch
Built InsightRAG: hybrid RAG + text-to-SQL over documents and operational data. Router picks docs/SQL/hybrid. Hybrid retrieval (BM25 + dense). Postgres/pgvector or SQLite fallback. Golden eval: 100% route accuracy, 100% source recall, 100% SQL validity.

## Architecture (draw this)
User → FastAPI → Router → [Retrieval | SQL Agent] → LLM → Answer + citations/SQL

## Top Q&A

**Walk through a query.** Router classifies → retrieval embeds + hybrid search top-k → context with [1][2] citations → LLM answer OR SQL agent generates read-only SELECT → results formatted.

**Why hybrid search?** Dense misses exact terms ($50, AES-256); BM25 misses paraphrases. Fuse with min-max normalized scores (ADR-0001).

**Why Postgres + pgvector?** Production-grade storage, single data plane for warehouse + vectors, swappable via `INSIGHTRAG_DATABASE_URL`. SQLite works for zero-setup demos.

**How prevent SQL injection?** Single statement only; `is_read_only()` rejects non-SELECT; Postgres role should be read-only in prod.

**How prevent hallucinations?** Ground in retrieved chunks; system prompt; citations; guardrails planned for production tier.

**Offline vs online?** Provider abstraction (`Embeddings`, `LLM`). No key → hashing embeddings + extractive answers. With key → OpenAI embeddings + synthesized answers.

**What broke during build?** Router at 84% — doc questions with "how many" misrouted to SQL. Fixed with doc-override terms → 100%.

**Keyword metric at 50%?** Old metric checked answer text only. Offline answers are extractive. `keyword_in_grounded` (answer + citations) is 100%.

**What's next?** LangGraph multi-agent, cross-encoder reranker, guardrails, cloud deploy, reconciliation agent.

## Demo questions (memorize)
1. What is ERA? → docs + mlb_glossary.md citation
2. Who hit the most home runs in 1998? → sql + batting leaderboard
3. What is WAR and who led MLB in WAR in 1998? → hybrid (definition + SQL)

## Files to point at
- `app/vector_store.py` — hybrid retrieval
- `app/router.py` — routing
- `app/sql_agent.py` — text-to-SQL
- `app/pipeline.py` — orchestration
- `scripts/evaluate.py` — metrics
- `docs/adr/0001-*` — design decisions
