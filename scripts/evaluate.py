"""Evaluation harness over the golden Q/A set."""

from __future__ import annotations

import json
import statistics
from pathlib import Path

from app.config import Settings, get_settings
from app.pipeline import AnswerResult, Assistant


def _load_golden(data_dir: Path) -> list[dict]:
    return json.loads((data_dir / "golden_qa.json").read_text())


def _grounded_text(result: AnswerResult) -> str:
    parts = [result.answer]
    for c in result.citations:
        parts.append(c.snippet)
    return " ".join(parts).lower()


def evaluate(settings: Settings | None = None) -> dict:
    settings = settings or get_settings()
    assistant = Assistant(settings)
    golden = _load_golden(Path(settings.data_dir))

    route_correct = 0
    doc_total = 0
    source_hits = 0
    kw_total = 0
    kw_in_answer = 0
    kw_in_grounded = 0
    sql_total = 0
    sql_valid = 0
    sql_kw_total = 0
    sql_kw_hits = 0
    latencies: list[float] = []
    per_question: list[dict] = []

    for item in golden:
        result = assistant.answer(item["question"])
        latencies.append(result.latency_ms)
        issues: list[str] = []
        passed = True

        if result.route != item["route"]:
            passed = False
            issues.append(f"route: got {result.route}, expected {item['route']}")
        else:
            route_correct += 1

        if item["route"] == "docs":
            doc_total += 1
            cited = {c.source for c in result.citations}
            if item.get("expected_source") and item["expected_source"] not in cited:
                passed = False
                issues.append(f"missing source {item['expected_source']}")
            elif item.get("expected_source"):
                source_hits += 1
            answer_lc = result.answer.lower()
            grounded_lc = _grounded_text(result)
            for kw in item.get("expected_keywords", []):
                kw_total += 1
                k = kw.lower()
                if k in answer_lc:
                    kw_in_answer += 1
                else:
                    passed = False
                    issues.append(f"missing keyword in answer: {kw}")
                if k in grounded_lc:
                    kw_in_grounded += 1

        if item["route"] == "sql":
            sql_total += 1
            if result.sql and result.error is None and result.sql_columns is not None:
                sql_valid += 1
            else:
                passed = False
                issues.append("sql query failed")
            sql_lc = (result.sql or "").lower()
            for frag in item.get("expected_sql_contains", []):
                sql_kw_total += 1
                if frag.lower() in sql_lc:
                    sql_kw_hits += 1
                else:
                    passed = False
                    issues.append(f"sql missing fragment: {frag}")
            # Correctness check on the final answer text (robust to SQL variations).
            answer_lc = result.answer.lower()
            for kw in item.get("expected_answer_contains", []):
                kw_total += 1
                if kw.lower() in answer_lc:
                    kw_in_answer += 1
                else:
                    passed = False
                    issues.append(f"answer missing: {kw}")

        if item["route"] == "meta":
            answer_lc = result.answer.lower()
            for kw in item.get("expected_keywords", []):
                kw_total += 1
                if kw.lower() in answer_lc:
                    kw_in_answer += 1
                else:
                    passed = False
                    issues.append(f"missing keyword: {kw}")

        if item["route"] == "hybrid":
            answer_lc = result.answer.lower()
            grounded_lc = _grounded_text(result)
            for kw in item.get("expected_keywords", []):
                kw_total += 1
                k = kw.lower()
                if k in answer_lc or k in grounded_lc:
                    kw_in_answer += 1
                else:
                    passed = False
                    issues.append(f"missing hybrid keyword: {kw}")
            if result.sql and result.error is None:
                sql_valid += 1
                sql_total += 1
            else:
                passed = False
                issues.append("hybrid sql failed")
            sql_lc = (result.sql or "").lower()
            for frag in item.get("expected_sql_contains", []):
                sql_kw_total += 1
                if frag.lower() in sql_lc:
                    sql_kw_hits += 1
                else:
                    passed = False
                    issues.append(f"sql missing fragment: {frag}")
            for kw in item.get("expected_answer_contains", []):
                kw_total += 1
                if kw.lower() in answer_lc or kw.lower() in grounded_lc:
                    kw_in_answer += 1
                else:
                    passed = False
                    issues.append(f"answer missing: {kw}")

        per_question.append(
            {
                "question": item["question"],
                "expected_route": item["route"],
                "actual_route": result.route,
                "passed": passed,
                "issues": issues,
                "answer_preview": result.answer[:160].replace("\n", " | "),
            }
        )

    def pct(a: int, b: int) -> float:
        return round(100.0 * a / b, 1) if b else 0.0

    latencies_sorted = sorted(latencies)
    p50 = statistics.median(latencies_sorted) if latencies_sorted else 0.0
    p95 = (
        latencies_sorted[int(0.95 * (len(latencies_sorted) - 1))]
        if latencies_sorted
        else 0.0
    )

    return {
        "mode": "offline" if settings.is_offline else "online",
        "database": "postgres" if settings.uses_postgres else "sqlite",
        "index_backend": settings.index_backend,
        "total_questions": len(golden),
        "questions_passed": sum(1 for q in per_question if q["passed"]),
        "route_accuracy": pct(route_correct, len(golden)),
        "source_recall_at_k": pct(source_hits, doc_total),
        "keyword_in_answer": pct(kw_in_answer, kw_total),
        "keyword_in_grounded": pct(kw_in_grounded, kw_total),
        "sql_validity": pct(sql_valid, sql_total),
        "sql_keyword_match": pct(sql_kw_hits, sql_kw_total),
        "latency_p50_ms": round(p50, 1),
        "latency_p95_ms": round(p95, 1),
        "per_question": per_question,
    }


def write_metrics_md(metrics: dict, path: Path | None = None) -> None:
    path = path or Path("docs/METRICS.md")
    path.parent.mkdir(parents=True, exist_ok=True)
    passed = metrics.get("questions_passed", 0)
    total = metrics["total_questions"]
    lines = [
        "# InsightRAG Evaluation Metrics",
        "",
        f"Mode: **{metrics['mode']}** | DB: **{metrics['database']}** | "
        f"Index: **{metrics['index_backend']}** | Questions: **{total}** | "
        f"Passed: **{passed}/{total}**",
        "",
        "| Metric | Value | Notes |",
        "|--------|-------|-------|",
        f"| Route accuracy | {metrics['route_accuracy']}% | Router picked expected path |",
        f"| Source recall@k | {metrics['source_recall_at_k']}% | Expected doc in citations |",
        f"| Keyword in answer | {metrics['keyword_in_answer']}% | In final answer text |",
        f"| Keyword in grounded text | {metrics['keyword_in_grounded']}% | Answer + citation snippets |",
        f"| SQL validity | {metrics['sql_validity']}% | Read-only query succeeded |",
        f"| SQL keyword match | {metrics['sql_keyword_match']}% | Expected SQL fragments |",
        f"| Latency p50 | {metrics['latency_p50_ms']} ms | |",
        f"| Latency p95 | {metrics['latency_p95_ms']} ms | |",
        "",
    ]
    failures = [q for q in metrics.get("per_question", []) if not q["passed"]]
    if failures:
        lines.extend(["## Per-question failures", ""])
        for item in failures:
            lines.append(f"- **{item['question']}** — {', '.join(item['issues'])}")
        lines.append("")
    lines.append("_Generated by `python -m scripts.evaluate`._")
    lines.append("")
    path.write_text("\n".join(lines))


def main() -> None:
    metrics = evaluate()
    for k, v in metrics.items():
        print(f"{k:24s}: {v}")
    suffix = metrics["mode"]
    write_metrics_md(metrics, Path(f"docs/METRICS_{suffix.upper()}.md"))
    write_metrics_md(metrics, Path("docs/METRICS.md"))
    print(f"\nWrote docs/METRICS.md and docs/METRICS_{suffix.upper()}.md")


if __name__ == "__main__":
    main()
