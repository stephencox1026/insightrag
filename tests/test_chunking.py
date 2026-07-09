from app.chunking import chunk_text


def test_chunking_produces_overlapping_chunks():
    text = "sentence one. " * 200
    chunks = chunk_text(text, source="doc.md", title="Doc", chunk_size=200, overlap=50)
    assert len(chunks) > 1
    assert all(c.source == "doc.md" for c in chunks)
    ids = [c.id for c in chunks]
    assert len(ids) == len(set(ids))


def test_chunking_empty_text():
    assert chunk_text("", source="d", title="t") == []


def test_chunking_short_text_single_chunk():
    text = "Short policy note."
    chunks = chunk_text(text, source="a.md", title="A")
    assert len(chunks) == 1
    assert chunks[0].text == text


def test_markdown_splits_on_headers():
    md = "# Title\n\nIntro paragraph.\n\n## Section A\n\nContent A here.\n\n## Section B\n\nContent B here."
    chunks = chunk_text(md, source="p.md", title="P", chunk_size=400, overlap=40)
    assert len(chunks) >= 2
    combined = " ".join(c.text for c in chunks)
    assert "Content A" in combined
    assert "Content B" in combined


def test_chunking_no_infinite_loop_on_repetitive_text():
    text = "word " * 5000
    chunks = chunk_text(text, source="w.md", title="W", chunk_size=100, overlap=20)
    assert len(chunks) > 10
    assert len(chunks) < 2000
