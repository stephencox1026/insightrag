"""Exercise online mode: requires OPENAI_API_KEY in environment or .env.

Runs a small smoke test (3 doc + 3 SQL questions) then full eval if --full.

Usage:
    OPENAI_API_KEY=sk-... python -m scripts.test_online
    OPENAI_API_KEY=sk-... python -m scripts.test_online --full
"""

from __future__ import annotations

import os
import sys

from app.config import get_settings
from app.pipeline import Assistant
from scripts.evaluate import evaluate, write_metrics_md

SMOKE = [
    ("docs", "What is ERA?"),
    ("docs", "How is OPS calculated?"),
    ("docs", "How many plate appearances are typically needed to qualify for the batting title?"),
    ("sql", "Who hit the most home runs in 1998?"),
    ("sql", "What was the Yankees' record in 1998?"),
    ("sql", "Who led MLB in WAR in 1998?"),
]


def main() -> None:
    full = "--full" in sys.argv
    settings = get_settings()
    settings.offline = False  # force online attempt

    if not settings.openai_api_key:
        print("ERROR: Set OPENAI_API_KEY in .env or environment.")
        sys.exit(1)

    os.environ["INSIGHTRAG_OFFLINE"] = "false"
    get_settings.cache_clear()
    settings = get_settings()

    print(f"Online mode | DB: {'postgres' if settings.uses_postgres else 'sqlite'}")
    assistant = Assistant(settings)

    print("\n==> Smoke test")
    failed = 0
    for expected_route, question in SMOKE:
        result = assistant.answer(question)
        ok = result.route == expected_route and not result.error
        status = "OK" if ok else "FAIL"
        print(f"  [{status}] route={result.route} latency={result.latency_ms}ms | {question[:50]}")
        if not ok:
            failed += 1
            if result.error:
                print(f"         error: {result.error}")

    if failed:
        print(f"\n{failed} smoke test(s) failed.")
        sys.exit(1)

    print("\nAll smoke tests passed.")

    if full:
        print("\n==> Full golden-set eval (online)")
        metrics = evaluate(settings)
        for k, v in metrics.items():
            print(f"  {k:24s}: {v}")
        write_metrics_md(metrics)
        write_metrics_md(metrics, __import__("pathlib").Path("docs/METRICS_ONLINE.md"))
        print("\nWrote docs/METRICS_ONLINE.md")


if __name__ == "__main__":
    main()
