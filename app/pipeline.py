"""End-to-end orchestration: route -> retrieve/query -> generate grounded answer."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np

from .answer_format import (
    compose_hybrid_answer,
    doc_question_for_hybrid,
    polish_answer_text,
    polish_doc_answer,
    polish_sql_answer,
)
from .capabilities import capabilities_answer, match_meta_intent
from .config import Settings, get_settings
from .embeddings import Embeddings, get_embeddings
from .llm import _FALLBACK_ANSWER, LLM, OfflineLLM, get_llm
from .reconciliation import format_reconciliation_note, reconcile_hybrid
from .router import Route, route_query
from .runtime import resolve_llm_offline, resolve_offline
from .sql_agent import SQLAgent
from .sql_format import verbalize_sql
from .vector_store import RetrievedChunk, get_vector_index


@dataclass
class Citation:
    marker: int
    source: str
    title: str
    snippet: str
    score: float


@dataclass
class AnswerResult:
    question: str
    answer: str
    route: str
    citations: list[Citation] = field(default_factory=list)
    sql: str | None = None
    sql_columns: list[str] | None = None
    sql_rows: list[list] | None = None
    latency_ms: float = 0.0
    offline: bool = False
    error: str | None = None
    reconciliation_summary: str | None = None


def _format_context(chunks: list[RetrievedChunk]) -> str:
    blocks = []
    for i, rc in enumerate(chunks, start=1):
        blocks.append(f"[{i}] ({rc.chunk.title}) {rc.chunk.text}")
    return "\n\n".join(blocks)


def _is_out_of_scope(question: str) -> bool:
    q = question.lower()
    return any(
        term in q
        for term in (
            "weather",
            "stock price",
            "bitcoin price",
            "live score",
            "today's game",
            "today's scores",
            "today's mlb",
            "tonight's game",
            "current season",
            "this season",
            "latest scores",
        )
    )


class Assistant:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.settings.ensure_dirs()
        self.index = get_vector_index(self.settings)
        if self.index.exists():
            self.index.load()
        index_dim = int(
            self.index.meta.get("dim")
            or (self.index.vectors.shape[1] if self.index.vectors.size else 0)
        )
        # Retrieval stays hashing-aligned with the index; LLM/SQL can go online
        # whenever an API key is present (even if the index was built offline).
        self._retrieval_offline = resolve_offline(
            self.settings, self.index.meta, index_dim
        )
        self._offline = resolve_llm_offline(self.settings)
        self.embeddings: Embeddings = get_embeddings(
            self.settings, offline=self._retrieval_offline
        )
        self.llm: LLM = get_llm(self.settings, offline=self._offline)
        self.sql_agent = SQLAgent(
            settings=self.settings,
            llm=self.llm,
            offline=self._offline,
        )

    def retrieve(self, question: str) -> list[RetrievedChunk]:
        if not self.index.chunks:
            return []
        qvec = self.embeddings.embed([question])[0]
        return self.index.search(
            question,
            np.asarray(qvec),
            top_k=self.settings.top_k,
            alpha=self.settings.hybrid_alpha,
        )

    def _answer_docs(
        self,
        question: str,
        *,
        max_sentences: int = 2,
        raw_for_compose: bool = False,
    ) -> AnswerResult:
        chunks = self.retrieve(question)
        context = _format_context(chunks)
        if isinstance(self.llm, OfflineLLM):
            max_sents = max_sentences if raw_for_compose else (1 if len(question) < 120 else 2)
            raw = self.llm.answer(question, context, max_sentences=max_sents)
            answer = raw if raw_for_compose else polish_doc_answer(raw, question)
        else:
            answer = self.llm.answer(question, context)
        citations = [
            Citation(
                marker=i,
                source=rc.chunk.source,
                title=rc.chunk.title,
                snippet=rc.chunk.text[:400],
                score=round(rc.score, 4),
            )
            for i, rc in enumerate(chunks, start=1)
        ]
        return AnswerResult(
            question=question,
            answer=answer,
            route=Route.DOCS.value,
            citations=citations,
        )

    def _answer_sql(self, question: str) -> AnswerResult:
        sql_ans = self.sql_agent.answer(question)
        if sql_ans.error or sql_ans.result is None:
            detail = sql_ans.error or "No rows returned."
            return AnswerResult(
                question=question,
                answer=f"I couldn't answer that from the 1998 MLB data.\n\n{detail}",
                route=Route.SQL.value,
                sql=sql_ans.sql or None,
                error=sql_ans.error,
            )
        res = sql_ans.result
        rows = [list(r) for r in res.rows]
        answer = verbalize_sql(res.columns, rows)
        if self._offline:
            answer = polish_sql_answer(answer)
        return AnswerResult(
            question=question,
            answer=answer,
            route=Route.SQL.value,
            sql=res.sql,
            sql_columns=res.columns,
            sql_rows=rows,
        )

    def _answer_hybrid(self, question: str) -> AnswerResult:
        doc_q = doc_question_for_hybrid(question)
        docs = self._answer_docs(doc_q, max_sentences=3, raw_for_compose=self._offline)
        sql = self._answer_sql(question)

        if self._offline:
            combined = compose_hybrid_answer(question, docs.answer, sql.answer)
            policy_line = combined.split("\n\n")[0]
            report = reconcile_hybrid(policy_line, sql.answer, question)
            note = format_reconciliation_note(report)
            if note:
                combined += note
        else:
            system = (
                "You are a precise assistant. Synthesize a single concise answer "
                "using BOTH the documentation excerpt and the SQL results. Cite "
                "doc sources with [n] markers when used. If sources conflict, say so."
            )
            user = (
                f"Documentation:\n{docs.answer}\n\n"
                f"SQL results:\n{sql.answer}\n\n"
                f"Question: {question}\n\nAnswer:"
            )
            combined = self.llm.complete(system, user)
            report = reconcile_hybrid(docs.answer, sql.answer, question)

        return AnswerResult(
            question=question,
            answer=combined,
            route=Route.HYBRID.value,
            citations=docs.citations,
            sql=sql.sql,
            sql_columns=sql.sql_columns,
            sql_rows=sql.sql_rows,
            error=sql.error,
            reconciliation_summary=report.summary,
        )

    def _answer_meta(self, question: str) -> AnswerResult:
        text = capabilities_answer(question, self.settings)
        return AnswerResult(
            question=question,
            answer=text,
            route="meta",
        )

    def answer(self, question: str) -> AnswerResult:
        start = time.perf_counter()
        if _is_out_of_scope(question):
            result = AnswerResult(
                question=question,
                answer=_FALLBACK_ANSWER,
                route=Route.DOCS.value,
            )
        elif match_meta_intent(question):
            result = self._answer_meta(question)
        else:
            route = route_query(question)
            if route is Route.SQL:
                result = self._answer_sql(question)
            elif route is Route.HYBRID:
                result = self._answer_hybrid(question)
            else:
                result = self._answer_docs(question)
        result.latency_ms = round((time.perf_counter() - start) * 1000, 1)
        result.offline = self._offline
        result.answer = polish_answer_text(result.answer, question)
        return result
