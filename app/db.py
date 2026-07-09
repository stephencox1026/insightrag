"""Database connection helpers for SQLite and Postgres."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from .config import Settings


@contextmanager
def connect(settings: Settings) -> Iterator[Any]:
    """Yield a DB connection (sqlite3 or psycopg)."""
    if settings.uses_postgres:
        import psycopg

        with psycopg.connect(settings.database_url) as conn:
            yield conn
    else:
        import sqlite3

        conn = sqlite3.connect(settings.db_path)
        try:
            yield conn
        finally:
            conn.close()


def warehouse_ready(settings: Settings) -> bool:
    """True if the operational warehouse has been seeded."""
    try:
        with connect(settings) as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM batting")
            row = cur.fetchone()
            count = row[0] if row else 0
            return count > 0
    except Exception:
        return False


def index_ready(settings: Settings) -> bool:
    if settings.uses_postgres:
        try:
            with connect(settings) as conn:
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM document_chunks")
                row = cur.fetchone()
                return bool(row and row[0] > 0)
        except Exception:
            return False
    return (settings.index_dir / "vectors.npy").exists()
