"""Shared test fixtures.

Tests force OFFLINE mode and use a temporary data directory so they run with no
API key and never touch the developer's real index/warehouse.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture(scope="session", autouse=True)
def offline_env(tmp_path_factory: pytest.TempPathFactory) -> None:
    tmp = tmp_path_factory.mktemp("insightrag_data")
    os.environ["INSIGHTRAG_OFFLINE"] = "true"
    os.environ.pop("OPENAI_API_KEY", None)
    os.environ["INSIGHTRAG_DATABASE_URL"] = ""
    os.environ["INSIGHTRAG_DATA_DIR"] = str(tmp)
    os.environ["INSIGHTRAG_INDEX_DIR"] = str(tmp / "index")
    os.environ["INSIGHTRAG_DB_PATH"] = str(tmp / "warehouse.db")

    # Copy sample docs into the temp data dir so ingestion has content.
    src_docs = Path(__file__).resolve().parents[1] / "data" / "docs"
    dst_docs = tmp / "docs"
    dst_docs.mkdir(parents=True, exist_ok=True)
    for p in src_docs.glob("*.md"):
        (dst_docs / p.name).write_text(p.read_text())

    # Clear cached settings so env vars take effect.
    from app.config import get_settings

    get_settings.cache_clear()


@pytest.fixture(scope="session")
def built(offline_env: None):
    """Seed warehouse + build index once for the test session."""
    from app.config import get_settings
    from app.db import connect
    from app.ingest import build_index
    from app.warehouse import init_warehouse

    settings = get_settings()
    settings.ensure_dirs()
    init_warehouse(settings)

    # Tests avoid network. Insert a minimal in-memory 1998-like dataset.
    with connect(settings) as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO players VALUES (?,?,?,?,?,?,?)",
            ("mcgwima01", "Mark", "McGwire", "Mark McGwire", "R", "R", "1986-08-01"),
        )
        cur.execute(
            "INSERT INTO players VALUES (?,?,?,?,?,?,?)",
            ("martipe02", "Pedro", "Martinez", "Pedro Martínez", "R", "R", "1992-09-24"),
        )
        cur.execute(
            "INSERT INTO teams VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            ("NYA", "New York Yankees", "AL", "E", 114, 48, 0.704, 965, 656, 3381211, "Yankee Stadium"),
        )
        cur.execute(
            "INSERT INTO teams VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            ("SLN", "St. Louis Cardinals", "NL", "C", 83, 79, 0.512, 845, 874, 3447291, "Busch Stadium"),
        )
        cur.execute(
            "INSERT INTO batting VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("mcgwima01", "SLN", 1, 155, 509, 101, 152, 21, 0, 70, 147, 1, 162, 155, 1, 3),
        )
        cur.execute(
            "INSERT INTO pitching VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("martipe02", "BOS", 1, 19, 7, 2.89, 33, 33, 0, 251, 57, 196, 17, 713, 70),
        )
        cur.execute(
            "INSERT INTO fangraphs_batting VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("Mark McGwire", "STL", 681, 509, 152, 70, 147, 0.299, 0.470, 0.752, 1.222, 0.503, 205, 8.5),
        )
        conn.commit()

    build_index(settings)
    return settings
