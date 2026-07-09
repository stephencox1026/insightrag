"""FastAPI service exposing the assistant."""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import asdict

from fastapi import FastAPI
from pydantic import BaseModel, Field

from .config import get_settings
from .db import index_ready, warehouse_ready
from .pipeline import Assistant

logging.basicConfig(
    level=logging.INFO,
    format='{"level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}',
)
logger = logging.getLogger("insightrag")

app = FastAPI(title="InsightRAG", version="0.2.0")

_assistant: Assistant | None = None


def get_assistant() -> Assistant:
    global _assistant
    if _assistant is None:
        _assistant = Assistant()
    return _assistant


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)


@app.get("/health")
def health() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "version": app.version,
        "mode": "offline" if settings.is_offline else "online",
        "database": "postgres" if settings.uses_postgres else "sqlite",
        "index_backend": settings.index_backend,
    }


@app.get("/ready")
def ready() -> dict:
    settings = get_settings()
    wh = warehouse_ready(settings)
    idx = index_ready(settings)
    return {
        "ready": bool(wh and idx),
        "warehouse_ready": wh,
        "index_ready": idx,
    }


@app.post("/query")
def query(req: QueryRequest) -> dict:
    request_id = str(uuid.uuid4())[:8]
    start = time.perf_counter()
    assistant = get_assistant()
    result = assistant.answer(req.question)
    latency_ms = round((time.perf_counter() - start) * 1000, 1)
    logger.info(
        "request_id=%s route=%s latency_ms=%s offline=%s q=%r",
        request_id,
        result.route,
        latency_ms,
        result.offline,
        req.question[:120],
    )
    payload = asdict(result)
    payload["request_id"] = request_id
    return payload
