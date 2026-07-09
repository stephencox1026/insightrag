"""Document chunking utilities.

Markdown-aware: splits on `##` section headers first, then applies char-based
chunking with overlap inside each section. Includes safety guards against
infinite loops and duplicate empty chunks.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_HEADER_RE = re.compile(r"^## .+", re.MULTILINE)


@dataclass
class Chunk:
    id: str
    text: str
    source: str
    title: str
    chunk_index: int


def _split_sections(text: str) -> list[str]:
    """Split markdown on ## headers; keep preamble + sections."""
    parts = _HEADER_RE.split(text)
    headers = _HEADER_RE.findall(text)
    if not headers:
        return [text]
    sections: list[str] = []
    if parts[0].strip():
        sections.append(parts[0].strip())
    for header, body in zip(headers, parts[1:], strict=False):
        combined = f"{header}\n{body}".strip()
        if combined:
            sections.append(combined)
    return sections or [text]


def chunk_text(
    text: str,
    source: str,
    title: str,
    chunk_size: int = 800,
    overlap: int = 120,
) -> list[Chunk]:
    text = text.strip()
    if not text:
        return []
    if overlap >= chunk_size:
        overlap = max(1, chunk_size // 4)

    sections = _split_sections(text) if "## " in text else [text]
    chunks: list[Chunk] = []
    idx = 0
    for section in sections:
        for piece in _chunk_section(section, chunk_size, overlap):
            chunks.append(
                Chunk(
                    id=f"{source}::{idx}",
                    text=piece,
                    source=source,
                    title=title,
                    chunk_index=idx,
                )
            )
            idx += 1
    return chunks


def _chunk_section(text: str, chunk_size: int, overlap: int) -> list[str]:
    text = text.strip()
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]

    pieces: list[str] = []
    seen_spans: set[tuple[int, int]] = set()
    start = 0
    n = len(text)
    max_iters = max(n // max(1, chunk_size - overlap) + 2, 1)
    iters = 0

    while start < n and iters < max_iters:
        iters += 1
        end = min(start + chunk_size, n)
        if end < n:
            window = text[start:end]
            for sep in ("\n\n", ". ", ".\n", "\n", "; ", " "):
                pos = window.rfind(sep)
                if pos > chunk_size * 0.4:
                    end = start + pos + len(sep)
                    break
        piece = text[start:end].strip()
        span = (start, end)
        if piece and span not in seen_spans:
            seen_spans.add(span)
            pieces.append(piece)
        if end >= n:
            break
        next_start = end - overlap
        if next_start <= start:
            next_start = start + max(1, chunk_size - overlap)
        start = next_start

    return pieces
