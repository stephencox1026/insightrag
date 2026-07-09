# Tool Cheat Sheet

## LangGraph (planned production tier)
- **Role:** Multi-agent planner/retrieval/SQL/critic
- **Why not yet:** Rule router hits 100% on golden set; LangGraph is next upgrade
- **One-liner:** "Replacing rule router with explicit agent graph for ambiguous queries"

## pgvector + Postgres
- **Role:** Warehouse + document embeddings in one DB
- **Why:** Production data plane; SQL agent and retrieval share infrastructure
- **Config:** `INSIGHTRAG_DATABASE_URL=postgresql://...`
- **One-liner:** "Vectors and operational data in Postgres; hybrid BM25 still in-memory"

## rank-bm25
- **Role:** Keyword leg of hybrid retrieval
- **Why not pure vector:** Exact-term matching for policy numbers, dollar amounts
- **One-liner:** "BM25 + dense fusion with min-max normalization"

## OpenAI (embeddings + chat)
- **Role:** `text-embedding-3-small` + `gpt-4o-mini` when key set
- **Fallback:** HashingEmbeddings + extractive OfflineLLM
- **One-liner:** "Provider abstraction — same pipeline, online or offline"

## FastAPI
- **Role:** `/health`, `/ready`, `/query` microservice
- **One-liner:** "Structured JSON with citations, SQL, latency, request_id"

## RAGAS (planned CI gate)
- **Role:** Faithfulness, context precision on golden set
- **Current:** Custom eval in `scripts/evaluate.py`

## Streamlit
- **Role:** Chat UI; `INSIGHTRAG_API_URL` routes through API when set

## Docker Compose
- **Role:** `pgvector/pgvector:pg16` on :5432
- **Commands:** `make docker-up`, `make demo-docker`
