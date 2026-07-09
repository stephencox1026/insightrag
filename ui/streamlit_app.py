"""Streamlit chat UI — in-process or via FastAPI when INSIGHTRAG_API_URL is set."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import requests
import streamlit as st
import streamlit.components.v1 as components

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.answer_format import answer_to_html  # noqa: E402
from app.capabilities import data_coverage  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db import index_ready, warehouse_ready  # noqa: E402
from app.pipeline import Assistant  # noqa: E402

st.set_page_config(page_title="Stephen Cox Chat Bot", page_icon="🔎", layout="centered")

st.markdown(
    """
    <style>
    [data-testid="stChatMessageAvatarUser"],
    [data-testid="stChatMessageAvatarAssistant"] {
        background: transparent !important;
        border: none !important;
        width: 2rem;
        height: 2rem;
        min-width: 2rem;
        min-height: 2rem;
    }
    [data-testid="stChatMessage"] {
        gap: 0.65rem;
    }
    [data-testid="stChatMessage"].latest-turn-box {
        background: #ffffff !important;
        color: #1a1a1a !important;
        border: 1px solid #d9d9d9;
        border-radius: 10px;
        padding: 0.85rem 1rem;
        margin: 0.35rem 0 0.15rem 0;
        box-shadow: 0 1px 4px rgba(0, 0, 0, 0.1);
    }
    [data-testid="stChatMessage"].latest-turn-box p,
    [data-testid="stChatMessage"].latest-turn-box span,
    [data-testid="stChatMessage"].latest-turn-box div {
        color: #1a1a1a !important;
    }
    #chat-end {
        height: 1px;
        scroll-margin-bottom: 140px;
    }
    [data-testid="stChatMessageAvatarUser"] img,
    [data-testid="stChatMessageAvatarAssistant"] img {
        width: 2rem;
        height: 2rem;
        border-radius: 50%;
        object-fit: cover;
    }
    [data-testid="stSidebar"] .sidebar-meta {
        margin: 0;
        padding: 0;
        line-height: 1.35;
    }
    [data-testid="stSidebar"] .sidebar-meta .brand {
        font-size: 1.05rem;
        font-weight: 600;
        margin: 0 0 0.35rem 0;
    }
    [data-testid="stSidebar"] .sidebar-meta .status {
        font-size: 0.95rem;
        font-weight: 400;
        color: #ffffff;
        margin: 0 0 0.12rem 0;
    }
    [data-testid="stSidebar"] .sidebar-meta .data {
        font-size: 0.95rem;
        font-weight: 400;
        color: #ffffff;
        opacity: 1;
        margin: 0;
    }
    section[data-testid="stMain"] .block-container {
        max-width: 42rem !important;
        padding-top: 1.25rem;
        padding-bottom: 7rem;
        margin-left: auto !important;
        margin-right: auto !important;
    }
    [data-testid="stBottomBlockContainer"] {
        background: transparent;
    }
    [data-testid="stBottomBlockContainer"] > div {
        max-width: 42rem;
        margin-left: auto;
        margin-right: auto;
        padding-left: 1rem;
        padding-right: 1rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

EXAMPLE_PROMPTS = [
    "What level of data do you have?",
    "Who had the best OPS in the American League?",
    "Compare Mark McGwire and Sammy Sosa",
    "Which qualified hitters batted under .250?",
    "Which team had the worst pitching in 1998?",
    "What was the Braves' longest winning streak?",
]

DATA_SOURCE = "1998 MLB Season (pybaseball)"
_ASSETS = Path(__file__).resolve().parent / "assets"
USER_AVATAR = str(_ASSETS / "avatar-user.svg")
ASSISTANT_AVATAR = str(_ASSETS / "avatar-assistant.svg")


def scroll_to_bottom() -> None:
    components.html(
        """
        <script>
        (function () {
            const doc = window.parent.document;
            const highlightLatest = () => {
                const messages = doc.querySelectorAll('[data-testid="stChatMessage"]');
                messages.forEach((m) => m.classList.remove("latest-turn-box"));
                if (messages.length >= 2) {
                    messages[messages.length - 2].classList.add("latest-turn-box");
                }
            };
            const scrollAll = () => {
                highlightLatest();
                const main = doc.querySelector('section[data-testid="stMain"]');
                const appView = doc.querySelector('[data-testid="stAppViewContainer"]');
                const messages = doc.querySelectorAll('[data-testid="stChatMessage"]');
                const anchor = doc.getElementById("chat-end");

                if (messages.length > 0) {
                    messages[messages.length - 1].scrollIntoView({
                        behavior: "auto",
                        block: "end",
                        inline: "nearest",
                    });
                }
                if (anchor) {
                    anchor.scrollIntoView({ behavior: "auto", block: "end" });
                }
                [main, appView].forEach((el) => {
                    if (el) el.scrollTop = el.scrollHeight + 500;
                });
                doc.documentElement.scrollTop = doc.documentElement.scrollHeight;
                doc.body.scrollTop = doc.body.scrollHeight;
                window.parent.scrollTo(0, doc.body.scrollHeight + 500);
            };
            highlightLatest();
            scrollAll();
            [100, 250, 500, 900, 1400].forEach((ms) => setTimeout(scrollAll, ms));
        })();
        </script>
        """,
        height=0,
    )


def highlight_latest_question() -> None:
    components.html(
        """
        <script>
        (function () {
            const doc = window.parent.document;
            const messages = doc.querySelectorAll('[data-testid="stChatMessage"]');
            messages.forEach((m) => m.classList.remove("latest-turn-box"));
            if (messages.length >= 2) {
                messages[messages.length - 2].classList.add("latest-turn-box");
            }
        })();
        </script>
        """,
        height=0,
    )


def query_via_api(api_url: str, question: str) -> dict:
    resp = requests.post(
        f"{api_url.rstrip('/')}/query",
        json={"question": question},
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()


@st.cache_resource
def load_assistant(_offline: bool, _version: str = "8") -> Assistant:
    return Assistant()


@st.cache_data(show_spinner=False)
def get_data_coverage(_db_key: str, _version: str = "8") -> str:
    return data_coverage(get_settings())


def render_assistant_payload(turn: dict) -> None:
    answer = turn.get("answer", "")
    st.markdown(answer_to_html(answer), unsafe_allow_html=True)

    citations = turn.get("citations") or []
    if citations:
        with st.expander("Sources", expanded=False):
            for c in citations:
                st.markdown(f"**[{c['marker']}]** {c['title']} (`{c['source']}`)")

    if turn.get("sql"):
        with st.expander("SQL used", expanded=False):
            st.code(turn["sql"], language="sql")
            rows = turn.get("sql_rows") or []
            if rows:
                st.caption(f"{len(rows)} row(s) returned")

    if turn.get("error"):
        with st.expander("Details", expanded=False):
            st.write(turn["error"])

    if turn.get("reconciliation_summary"):
        with st.expander("Data check", expanded=False):
            st.write(turn["reconciliation_summary"])


def run_query(question: str) -> dict:
    if api_url:
        return query_via_api(api_url, question)
    from dataclasses import asdict

    return asdict(load_assistant(offline_mode, "8").answer(question))


settings = get_settings()
api_url = os.getenv("INSIGHTRAG_API_URL") or settings.api_url
# Sidebar badge: generative LLM unavailable (templates/extractive only).
offline_mode = settings.is_offline
ready = index_ready(settings) and warehouse_ready(settings)

if "history" not in st.session_state:
    st.session_state.history = []
if "scroll_pending" not in st.session_state:
    st.session_state.scroll_pending = False

with st.sidebar:
    if ready:
        status_html = (
            'Status: <span style="color:#6B9E78;font-weight:400;">Ready</span>'
        )
    else:
        status_html = (
            'Status: <span style="color:#C4A35A;font-weight:400;">Setup required</span>'
        )
    st.markdown(
        f"""
        <div class="sidebar-meta">
          <p class="brand">Stephen Cox Chat Bot</p>
          <p class="status">{status_html}</p>
          <p class="data">Data: {DATA_SOURCE}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if not ready:
        st.warning("Run `make demo` or `make demo-docker` first.")

    if ready:
        with st.expander("Data coverage", expanded=False):
            st.markdown(get_data_coverage(settings.db_path.as_posix()))

    if st.session_state.history and st.button("Clear chat", use_container_width=True):
        st.session_state.history = []
        st.session_state.scroll_pending = False
        st.rerun()

    st.divider()
    st.markdown("##### Examples")
    for example in EXAMPLE_PROMPTS:
        if st.button(example, key=f"ex_{example}", use_container_width=True):
            st.session_state.pending_prompt = example
            st.session_state.scroll_pending = True
            st.rerun()

st.title("Stephen Cox Chat Bot")
st.caption("1998 season reference docs and MLB stats.")

if ready and not st.session_state.history:
    st.info("Ask about home runs, ERA, standings, WAR, or try an example from the sidebar.")

prompt = st.session_state.pop("pending_prompt", None)
if not prompt:
    prompt = st.chat_input("Ask a question...")

if prompt:
    with st.spinner("Thinking..."):
        try:
            payload = run_query(prompt)
        except Exception as exc:
            err = str(exc).lower()
            if "insufficient_quota" in err or "rate limit" in err:
                st.error(
                    "OpenAI quota exceeded. Switch to Ollama "
                    "(INSIGHTRAG_LLM_PROVIDER=ollama) or offline mode and restart."
                )
            elif "connection" in err and "11434" in err:
                st.error(
                    "Could not reach Ollama. Run `brew services start ollama` "
                    "and ensure `ollama list` shows qwen2.5:7b."
                )
            else:
                st.error(f"Request failed: {exc}")
            st.stop()
    st.session_state.history.append({"q": prompt, **payload})
    st.session_state.scroll_pending = True
    st.rerun()

for turn in st.session_state.history:
    with st.chat_message("user", avatar=USER_AVATAR):
        st.write(turn["q"])
    with st.chat_message("assistant", avatar=ASSISTANT_AVATAR):
        render_assistant_payload(turn)

st.markdown('<div id="chat-end"></div>', unsafe_allow_html=True)

if st.session_state.history:
    highlight_latest_question()

if st.session_state.scroll_pending:
    scroll_to_bottom()
    st.session_state.scroll_pending = False
