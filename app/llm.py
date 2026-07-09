"""LLM providers for answer generation and text-to-SQL."""

from __future__ import annotations

import re
from typing import Protocol

from .answer_format import (
    _clean_sentence,
    _echoes_question,
    _is_near_duplicate,
    clean_markdown,
    strip_markdown,
)
from .config import Settings
from .embeddings import _tokenize

_FALLBACK_ANSWER = (
    "I couldn't find a clear answer in the 1998 MLB docs or data. "
    "Try asking about home runs, ERA, standings, WAR, or a player/team from 1998."
)

_MIN_CONFIDENCE = 0.12


class LLM(Protocol):
    def answer(self, question: str, context: str) -> str: ...

    def complete(self, system: str, user: str) -> str: ...


class OpenAILLM:
    def __init__(self, api_key: str, model: str) -> None:
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key)
        self._model = model

    def complete(self, system: str, user: str) -> str:
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.1,
        )
        return (resp.choices[0].message.content or "").strip()

    def answer(self, question: str, context: str) -> str:
        system = (
            "You are a precise assistant. Answer ONLY from the provided context. "
            "Cite sources inline using the bracketed [n] markers shown in the "
            "context. If the answer is not in the context, say you don't know."
        )
        user = f"Context:\n{context}\n\nQuestion: {question}\n\nAnswer:"
        return self.complete(system, user)


class OllamaLLM:
    """Local Ollama chat model — no cloud API key required."""

    def __init__(self, model: str, base_url: str = "http://127.0.0.1:11434") -> None:
        self._model = model
        self._base_url = base_url.rstrip("/")

    def complete(self, system: str, user: str) -> str:
        import requests

        resp = requests.post(
            f"{self._base_url}/api/chat",
            json={
                "model": self._model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "stream": False,
                "options": {"temperature": 0.1},
            },
            timeout=180,
        )
        resp.raise_for_status()
        payload = resp.json()
        return ((payload.get("message") or {}).get("content") or "").strip()

    def answer(self, question: str, context: str) -> str:
        system = (
            "You are a precise 1998 MLB assistant. Answer ONLY from the provided "
            "context. Cite sources inline using the bracketed [n] markers shown in "
            "the context. If the answer is not in the context, say you don't know."
        )
        user = f"Context:\n{context}\n\nQuestion: {question}\n\nAnswer:"
        return self.complete(system, user)


def _split_sentences(text: str) -> list[str]:
    clean = strip_markdown(text)
    parts = re.split(r"(?<=[.!?])\s+|\n+", clean)
    return [p.strip() for p in parts if p.strip()]


def _source_bonus(source: str, question: str) -> float:
    s = source.lower()
    q = question.lower()
    bonus = 0.0
    if any(w in q for w in ("what is", "definition", "define", "calculated", "formula")):
        if "glossary" in s:
            bonus += 0.45
    if any(w in q for w in ("qualify", "qualification", "batting title", "era title")):
        if "rules" in s or "faq" in s:
            bonus += 0.5
    if any(w in q for w in ("1998", "season", "postseason", "overview")):
        if "overview" in s:
            bonus += 0.35
    return bonus


def _score_sentence(sentence: str, question: str, *, source: str = "") -> float:
    q_tokens = set(_tokenize(question))
    s_tokens = set(_tokenize(sentence))
    if not q_tokens:
        return 0.0
    overlap = len(q_tokens & s_tokens) / len(q_tokens)
    bonus = _source_bonus(source, question)
    # Mild boost for sentences with concrete facts (numbers, percentages, etc.).
    if re.search(r"\$[\d,]+|\d+%|\d+(?:\.\d+)?", sentence):
        bonus += 0.35
    if len(sentence) > 200:
        bonus -= 0.2
    if re.match(r"^(Q:|A:)", sentence, re.I):
        bonus -= 1.0
    if re.match(r"^[•◦\-\*]", sentence):
        bonus -= 0.5
    if not re.search(r"[.!?]$", sentence):
        bonus -= 0.3
    if re.search(r"^internal policies for", sentence, re.I):
        bonus -= 0.5
    if "|" in sentence and re.search(r"\|\s*[-|]", sentence):
        bonus -= 0.6
    # Domain-specific heuristics are intentionally avoided here. The demo's data
    # domain can be swapped (e.g., Northwind -> MLB) without re-tuning.
    if _echoes_question(sentence, question):
        bonus -= 1.0
    if sentence.strip().endswith("?"):
        bonus -= 0.8
    return overlap + bonus


class OfflineLLM:
    """Extractive answers: pick the best sentences from retrieved context."""

    def complete(self, system: str, user: str) -> str:
        return ""

    def answer(self, question: str, context: str, *, max_sentences: int = 2) -> str:
        if not context.strip():
            return _FALLBACK_ANSWER

        scored: list[tuple[float, str]] = []
        blocks = [b.strip() for b in context.split("\n\n") if b.strip()]
        for block in blocks:
            title_m = re.match(r"^\[\d+\]\s*\(([^)]+)\)\s*", block)
            source = title_m.group(1) if title_m else ""
            body = re.sub(r"^\[\d+\]\s*\([^)]+\)\s*", "", block)
            body = clean_markdown(body)
            for sent in _split_sentences(body):
                if len(sent) < 25:
                    continue
                score = _score_sentence(sent, question, source=source)
                if score > 0.05:
                    scored.append((score, sent))

        if not scored:
            return _FALLBACK_ANSWER

        scored.sort(key=lambda x: -x[0])
        if scored[0][0] < _MIN_CONFIDENCE:
            return _FALLBACK_ANSWER

        picks: list[str] = []
        for _, sent in scored:
            sent = _clean_sentence(sent)
            if len(sent) < 25:
                continue
            if any(_is_near_duplicate(sent, pick) for pick in picks):
                continue
            if _echoes_question(sent, question):
                continue
            picks.append(sent)
            if len(picks) >= max_sentences:
                break

        if not picks:
            return _FALLBACK_ANSWER

        return picks[0] if len(picks) == 1 else " ".join(picks[:max_sentences])


def get_llm(settings: Settings, *, offline: bool | None = None) -> LLM:
    use_offline = settings.is_offline if offline is None else offline
    if use_offline:
        return OfflineLLM()
    if settings.uses_ollama:
        return OllamaLLM(model=settings.chat_model, base_url=settings.ollama_base_url)
    if not (settings.openai_api_key or "").strip():
        return OfflineLLM()
    return OpenAILLM(api_key=settings.openai_api_key, model=settings.chat_model)
