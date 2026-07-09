# Ship checklist — InsightRAG

Use this when publishing or refreshing the public demo.

## Local

```bash
cd insightrag
python3 -m venv .venv
make install
make demo
make ui          # http://localhost:8501
make test && make lint
```

## GitHub

```bash
git status
git push origin main
```

Repo: https://github.com/stephencox1026/insightrag

## Streamlit Cloud

1. Open [share.streamlit.io](https://share.streamlit.io) → **New app**
2. Repository: `stephencox1026/insightrag`
3. Branch: `main`
4. Main file path: `ui/cloud_app.py`
5. Python version: 3.11+ (default is fine)
6. Advanced → confirm `requirements.txt` is detected
7. Deploy — first boot runs `make demo` equivalent (1–3 minutes)
8. Live URL: _paste after deploy_

No secrets required for the offline demo (`INSIGHTRAG_OFFLINE=true` is set by the Cloud entrypoint). Document-only and catalog questions work without an API key; open-ended SQL synthesis needs a key or Ollama locally.

## Screenshots + Loom

1. Capture stills into `docs/screenshots/` (chat, Sources, SQL, catalog/meta)
2. Record ~3 min walkthrough with [docs/DEMO.md](DEMO.md)
3. Paste the Loom URL into README under **Demo video**

## Done when

- [ ] Public repo loads
- [ ] Live Cloud URL opens the chat UI
- [ ] README has live link + screenshots + Loom link
- [ ] `make demo && make ui` still works offline
