from app.answer_format import answer_to_html, normalize_display_answer, polish_answer_text
from app.pipeline import Assistant
from app.router import Route, route_query


def test_answer_to_html_escapes_dollar_signs():
    html_out = answer_to_html("The salary was $1,000,000.")
    assert "$1,000,000" in html_out
    assert "<p>" in html_out


def test_normalize_display_answer_strips_faq_bullets():
    raw = (
        "• A: WAR estimates value compared to replacement level.\n"
        "• WAR estimates value compared to replacement level.\n"
        "• What is WAR?"
    )
    cleaned = normalize_display_answer(raw, "What is WAR?")
    assert cleaned.count("replacement level") == 1
    assert "A:" not in cleaned
    assert "What is WAR" not in cleaned


def test_polish_answer_text_capitalizes_bullets():
    text = polish_answer_text("- customers table\n- products table")
    assert "- Customers" in text
    assert "- Products" in text


def test_router_classifies_routes():
    assert route_query("What is ERA?") == Route.DOCS
    assert route_query("Who hit the most home runs in 1998?") == Route.SQL
    assert route_query("What is WAR and who led MLB in WAR in 1998?") == Route.HYBRID


def test_doc_question_returns_clean_answer(built):
    assistant = Assistant(built)
    result = assistant.answer("What is ERA?")
    assert result.route == "docs"
    assert "A:" not in result.answer
    assert "•" not in result.answer
    assert "era" in result.answer.lower()


def test_doc_question_returns_grounded_citations(built):
    assistant = Assistant(built)
    result = assistant.answer("What is WAR?")
    assert result.route == "docs"
    assert result.citations, "expected at least one citation"
    assert any(c.source == "mlb_glossary.md" for c in result.citations)


def test_sql_home_run_leaders(built):
    assistant = Assistant(built)
    result = assistant.answer("Who hit the most home runs in 1998?")
    assert result.route == "sql"
    assert result.error is None
    assert result.sql_rows
    assert result.sql_rows[0][1] == 70
    assert "mcgwire" in result.answer.lower()


def test_sql_pedro_era(built):
    assistant = Assistant(built)
    result = assistant.answer("What was Pedro Martínez's ERA in 1998?")
    assert result.route == "sql"
    assert result.error is None
    assert "2.89" in result.answer


def test_hybrid_question_includes_reconciliation_summary(built):
    assistant = Assistant(built)
    result = assistant.answer("What is OPS and who had the highest OPS in 1998?")
    assert result.route == "hybrid"
    assert result.reconciliation_summary


def test_meta_help_mentions_mlb_and_sql(built):
    assistant = Assistant(built)
    result = assistant.answer("What can you help me with?")
    assert result.route == "meta"
    assert "mlb" in result.answer.lower() or "1998" in result.answer.lower()
    assert "sql" in result.answer.lower()


def test_out_of_scope_fallback(built):
    assistant = Assistant(built)
    result = assistant.answer("What's the weather today?")
    assert "couldn't find" in result.answer.lower()
