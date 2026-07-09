"""Tests for hybrid reconciliation."""

from app.reconciliation import reconcile_hybrid


def test_reconcile_hybrid_aligned_on_cancelled_count():
    report = reconcile_hybrid(
        "OPS is OBP plus SLG.",
        "Top results by OPS: 1. Mark McGwire — 1.222",
        "What is OPS and who had the highest OPS in 1998?",
    )
    assert report.aligned
    assert "no automatic cross-check" in report.summary.lower()
