.PHONY: help install docker-up docker-down demo demo-docker api ui eval test-online test lint clean

PY := .venv/bin/python
PIP := .venv/bin/pip

help:
	@echo "InsightRAG commands:"
	@echo "  make install       Install Python deps into .venv"
	@echo "  make docker-up     Start Postgres + pgvector (Docker)"
	@echo "  make docker-down   Stop Docker stack"
	@echo "  make demo          Seed SQLite + file index (no Docker)"
	@echo "  make demo-docker   Seed Postgres + pgvector (requires docker-up)"
	@echo "  make api           Run FastAPI on :8000"
	@echo "  make ui            Run Streamlit chat UI"
	@echo "  make eval          Run golden-set evaluation"
	@echo "  make test-online   Smoke test online mode (needs OPENAI_API_KEY)"
	@echo "  make test          Run pytest"
	@echo "  make lint          Run ruff"

install:
	$(PIP) install -r requirements-dev.txt

docker-up:
	docker compose up -d
	@echo "Waiting for Postgres..."
	@until docker compose exec -T postgres pg_isready -U insightrag -d insightrag >/dev/null 2>&1; do sleep 1; done
	@echo "Postgres ready."

docker-down:
	docker compose down

demo:
	$(PY) -m scripts.build_demo

demo-docker: docker-up
	@test -f .env || (echo "Missing .env — copy .env.example and set OPENAI_API_KEY for online mode." && exit 1)
	INSIGHTRAG_DATABASE_URL=postgresql://insightrag:insightrag@localhost:5432/insightrag $(PY) -m scripts.build_demo

api:
	.venv/bin/uvicorn app.api:app --reload --port 8000

ui:
	.venv/bin/streamlit run ui/streamlit_app.py

eval:
	$(PY) -m scripts.evaluate

test-online:
	$(PY) -m scripts.test_online --full

test:
	.venv/bin/pytest

lint:
	.venv/bin/ruff check app scripts tests ui

clean:
	rm -rf data/index data/warehouse.db .pytest_cache .ruff_cache
