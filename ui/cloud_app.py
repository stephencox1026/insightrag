"""Streamlit Cloud entrypoint.

Seeds the offline demo (warehouse + doc index) on first boot, then loads the
chat UI. Local use: prefer `make ui` after `make demo`.

Streamlit Cloud main file: ui/cloud_app.py
"""

from __future__ import annotations

import importlib.util
import os
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
# Cloud demo runs fully offline (no API keys required).
os.environ.setdefault("INSIGHTRAG_OFFLINE", "true")

import streamlit as st  # noqa: E402


def _demo_ready() -> bool:
    from app.config import get_settings
    from app.db import index_ready, warehouse_ready

    settings = get_settings()
    return warehouse_ready(settings) and index_ready(settings)


def ensure_demo() -> None:
    """Seed offline artifacts before any Streamlit UI calls."""
    if _demo_ready():
        return
    with st.spinner("First boot — seeding 1998 MLB warehouse + doc index…"):
        print("==> InsightRAG first boot — seeding offline demo…", flush=True)
        from scripts.build_demo import main as build_demo

        build_demo()


def _load_app() -> None:
    ensure_demo()
    app_path = ROOT / "ui" / "streamlit_app.py"
    spec = importlib.util.spec_from_file_location("insightrag_streamlit_app", app_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load chat UI from {app_path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["insightrag_streamlit_app"] = mod
    spec.loader.exec_module(mod)


try:
    _load_app()
except Exception as exc:  # noqa: BLE001
    st.set_page_config(page_title="InsightRAG — boot error", layout="centered")
    st.error("InsightRAG failed to start on Streamlit Cloud.")
    st.code(f"{type(exc).__name__}: {exc}")
    st.code(traceback.format_exc())
    raise
