"""One-command demo bootstrap."""

from __future__ import annotations

from app.config import get_settings
from app.ingest import build_index
from app.warehouse import init_warehouse, seed_warehouse


def main() -> None:
    settings = get_settings()
    settings.ensure_dirs()

    backend = "Postgres" if settings.uses_postgres else "SQLite"
    print(f"==> Loading 1998 MLB season warehouse ({backend})...")
    init_warehouse(settings)
    counts = seed_warehouse(settings)
    for table, n in counts.items():
        print(f"    {table:12s} {n:>6,} rows")

    print("\n==> Building document index...")
    try:
        stats = build_index(settings)
    except Exception as exc:  # noqa: BLE001
        err = str(exc).lower()
        if "insufficient_quota" in err or "rate limit" in err:
            print(
                "\nOpenAI API error (quota/billing). Options:\n"
                "  1. Add billing at https://platform.openai.com/account/billing\n"
                "  2. Run offline: set INSIGHTRAG_OFFLINE=true in .env and re-run make demo-docker\n"
            )
        raise
    print(f"    documents: {stats['documents']}")
    print(f"    chunks:    {stats['chunks']}")
    print(f"    backend:   {stats['backend']}")
    print(f"    provider:  {stats['provider']} (dim={stats['dim']})")
    print(f"    offline:   {stats['offline']}")

    mode = "OFFLINE (no API key)" if stats["offline"] else "ONLINE (OpenAI)"
    print(f"\nDemo ready in {mode} mode.")
    print("Start the API:  make api")
    print("Start the UI:   make ui")


if __name__ == "__main__":
    main()
