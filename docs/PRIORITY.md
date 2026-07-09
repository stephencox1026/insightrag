# Updated Priority List

## Completed
- [x] 1998 MLB warehouse schema + reference docs + golden eval harness
- [x] Hybrid BM25 + dense retrieval, router, SQL agent, meta handler
- [x] Consumer answer formatting + HTML rendering (no LaTeX `$` bugs)
- [x] Docker Compose + Postgres/pgvector (`make demo-docker`)
- [x] Reconciliation module for hybrid answers (`app/reconciliation.py`)
- [x] Per-question eval report in `scripts/evaluate.py`
- [x] Streamlit UI: centered layout, Clear chat, Sources/SQL/Data check expanders
- [x] Out-of-scope fallback + confidence threshold in offline mode
- [x] CI: ruff + pytest; interview docs (DEMO, INTERVIEW, STAR, TOOLS)

## P0 — Ship portfolio
1. [x] **Git commit + push** — public repo `stephencox1026/insightrag` (see `docs/SHIP.md`)
2. [x] **README screenshot gallery** + Streamlit Cloud bootstrap (`ui/cloud_app.py`)
3. [ ] **3-min Loom demo video** using `docs/DEMO.md` — paste URL into README
4. [ ] **Live Cloud URL** — deploy via SHIP.md, then commit URL into README
5. [ ] **Online eval** — `make test-online` → `docs/METRICS_ONLINE.md` (optional if API key set)

## P1 — Production tier
5. LangGraph multi-agent (planner, retrieval, SQL, critic, reconciliation)
6. Cross-encoder reranker
7. Guardrails (NeMo / Guardrails AI) + RAGAS in CI
8. Cloud deploy (Render/Railway) + live URL in README

## P2 — Enterprise (cherry-pick by job)
9. Event-driven ingest (Kafka / Celery)
10. LoRA fine-tune on golden Q/A
11. GraphRAG, Go microservice, EKS + Terraform

## Current metrics
See `docs/METRICS.md` — regenerate with `python -m scripts.evaluate` (online mode required for SQL questions).
