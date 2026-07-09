"""Reconciliation: compare doc claims with SQL results on hybrid answers.

For the MLB season demo, hybrid questions are typically "definition + stat" and
do not have a reliable one-to-one numeric cross-check. We keep a lightweight
placeholder so the UI can still show a "Data check" section without surfacing
misleading conflict warnings.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class ReconciliationClaim:
    label: str
    doc_value: str
    sql_value: str | None = None
    aligned: bool = True
    note: str = ""


@dataclass
class ReconciliationReport:
    aligned: bool
    claims: list[ReconciliationClaim] = field(default_factory=list)
    summary: str = ""


def _extract_money(text: str) -> str | None:
    m = re.search(r"\$[\d,.]+(?:\s*million)?", text, re.I)
    return m.group(0) if m else None


def _extract_percent(text: str) -> str | None:
    m = re.search(r"\d+%", text)
    return m.group(0) if m else None


def _extract_count_phrase(text: str, keyword: str) -> str | None:
    pattern = rf"(\d[\d,]*)\s+{keyword}"
    m = re.search(pattern, text, re.I)
    return m.group(1) if m else None


def reconcile_hybrid(doc_answer: str, sql_answer: str, question: str) -> ReconciliationReport:
    del doc_answer, sql_answer, question
    return ReconciliationReport(
        aligned=True,
        summary="No automatic cross-check is applied for MLB hybrid answers.",
    )


def format_reconciliation_note(report: ReconciliationReport) -> str:
    if report.aligned:
        return ""
    return f"\n\nNote: {report.summary}"
