# STAR Stories (from this build)

## 1. Router misclassification (Technical)
- **S:** Golden eval showed 84% route accuracy after MVP
- **T:** Fix routing without rewriting the pipeline
- **A:** Traced failures — "how many approvals for merge?" hit SQL signals. Added `DOC_OVERRIDE` for policy/doc terms
- **R:** Route accuracy 100% on 19-question golden set; documented in git history

## 2. Misleading keyword metric (Analytical)
- **S:** Keyword hit rate 50% but source recall 100%
- **T:** Eval should measure retrieval quality separately from answer phrasing
- **A:** Added `keyword_in_grounded` scoring answer + citation snippets; kept `keyword_in_answer` separate
- **R:** Grounded keyword 100%; honest reporting for offline extractive mode vs online synthesis

## 3. Infrastructure pivot (Engineering judgment)
- **S:** Plan assumed Docker/Postgres from day one; machine had no Docker initially
- **T:** Ship working MVP ASAP without blocking on infra
- **A:** Built SQLite + file index behind interfaces; added Postgres/pgvector path when Docker available
- **R:** `make demo` works anywhere; `make demo-docker` upgrades to production stack without code rewrites
