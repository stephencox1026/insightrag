import pytest

from app.warehouse import is_read_only, run_query


def test_read_only_guard_allows_select():
    assert is_read_only("SELECT * FROM batting")
    assert is_read_only("WITH x AS (SELECT 1) SELECT * FROM x")


def test_read_only_guard_blocks_mutations():
    assert not is_read_only("DELETE FROM batting")
    assert not is_read_only("DROP TABLE players")
    assert not is_read_only("SELECT 1; DELETE FROM batting")
    assert not is_read_only("UPDATE teams SET wins=0")


def test_query_runs_against_seeded_db(built):
    res = run_query(built, "SELECT COUNT(*) AS n FROM batting")
    assert res.columns == ["n"]
    assert res.rows[0][0] >= 1


def test_query_rejects_write(built):
    with pytest.raises(ValueError):
        run_query(built, "DELETE FROM batting")
