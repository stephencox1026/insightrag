# Docker Setup

InsightRAG uses **Postgres + pgvector** when `INSIGHTRAG_DATABASE_URL` is set.

## Prerequisites

1. Install [Docker Desktop](https://www.docker.com/products/docker-desktop/) for Mac.
2. Copy env file: `cp .env.example .env`
3. Set `OPENAI_API_KEY` in `.env` for online mode (optional for offline).

## Start Postgres

```bash
make docker-up          # starts pgvector/pg16 on localhost:5432
make demo-docker        # seeds warehouse + builds pgvector index
make eval               # run metrics
```

Connection string (already in `.env.example`):

```
INSIGHTRAG_DATABASE_URL=postgresql://insightrag:insightrag@localhost:5432/insightrag
```

## Stop Postgres

```bash
make docker-down
```

## SQLite fallback (no Docker)

```bash
unset INSIGHTRAG_DATABASE_URL   # or remove from .env
make demo
```

## Verify

```bash
curl -s localhost:8000/health    # after make api
# expect: "database": "postgres"
```
