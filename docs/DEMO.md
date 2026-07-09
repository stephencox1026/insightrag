# Demo Runbook (5 minutes)

A scripted path for a live interview demo. Rehearse once with a timer.

## Setup (before the call)
```bash
cd insightrag
python3 -m venv .venv && make install && make demo
make ui
```
Open **http://localhost:8502**. Confirm sidebar shows **Status: Ready**. Click **Clear chat** if you see old answers.

**Note:** open-ended MLB stats questions require **online mode** (set `OPENAI_API_KEY`). Offline mode still works for document-only questions (stat definitions and rules).

## The script

1. **Frame it (20s)**
   "This is the 1998 MLB assistant — Stephen Cox Chat Bot. It searches reference
   documents (stat definitions and rules) and queries a 1998 stats warehouse with
   read-only SQL. A router picks docs, SQL, hybrid, or a capabilities catalog for
   meta questions."

2. **Meta question (30s)** — ask:
   > What data do you have access to?

   Point out: 1998 MLB branding, doc sources, and the available SQL tables (batting, pitching, teams, standings, FanGraphs).

3. **Document question (45s)** — ask:
   > What is ERA?

   Point out: clear definition and formula. Expand **Sources** to show grounding.

4. **Data question (45s)** — ask:
   > Who hit the most home runs in 1998?

   Point out: leaderboard answer. Expand **SQL used**.

5. **Hybrid question (45s)** — ask:
   > What is WAR and who led MLB in WAR in 1998?

   Point out: definition + SQL result. Expand **Data check** (it will explain that no automatic cross-check is applied for MLB hybrids).

6. **Out-of-scope (15s)** — ask:
   > Give me today's MLB scores.

   Point out: polite fallback instead of hallucinating.

7. **Show the engineering (60s)**
   - `make eval` → `docs/METRICS.md`
   - `make test` → 28+ tests green
   - `app/sql_agent.py` — read-only text-to-SQL guardrail
   - `app/vector_store.py` — hybrid retrieval (vectors + BM25)

## Likely questions (have answers ready)
- *Why 1998 MLB?* A memorable season with rich, structured historical stats and clear “leaderboard” questions.
- *Why hybrid search?* Dense misses exact terms; BM25 misses paraphrases. (ADR 0001.)
- *How prevent SQL injection?* Single read-only SELECT; `is_read_only()` guardrail.
- *What would you build next?* LangGraph multi-agent graph, cross-encoder reranker, cloud deploy.
