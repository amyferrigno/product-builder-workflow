"""Test scripts/sql_guard.py."""

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from sql_guard import check_sql

REPO_ROOT = Path(__file__).parent.parent
PII = ["customers"]


def guard(sql, pii=None, max_rows=500, aggregate_only=True):
    return check_sql(sql, PII if pii is None else pii, max_rows, aggregate_only)


def test_plain_aggregate_select_is_allowed():
    assert guard("SELECT COUNT(*) FROM accounts") == []


def test_trailing_semicolon_is_allowed():
    assert guard("SELECT COUNT(*) FROM accounts;") == []


def test_with_select_is_allowed():
    sql = "WITH a AS (SELECT segment FROM accounts) SELECT segment, COUNT(*) FROM a GROUP BY segment"
    assert guard(sql) == []


@pytest.mark.parametrize("keyword", [
    "INSERT", "UPDATE", "DELETE", "MERGE", "DROP", "ALTER", "CREATE",
    "GRANT", "TRUNCATE", "REPLACE", "ATTACH", "PRAGMA",
])
def test_each_mutating_keyword_is_rejected(keyword):
    errors = guard(f"WITH x AS (SELECT COUNT(*) FROM accounts) {keyword} INTO t VALUES (1)")
    assert f"forbidden keyword: {keyword}" in errors


def test_keywords_are_case_insensitive():
    assert "forbidden keyword: DELETE" in guard("delete from accounts")


def test_delete_statement_is_not_a_select():
    errors = guard("DELETE FROM accounts")
    assert "only a single SELECT or WITH ... SELECT statement is allowed" in errors
    assert "forbidden keyword: DELETE" in errors


def test_keyword_inside_string_literal_is_allowed():
    assert guard("SELECT COUNT(*) AS c, 'drop table x' AS note FROM accounts") == []


def test_escaped_quote_inside_literal_is_handled():
    assert guard("SELECT COUNT(*) FROM accounts WHERE segment = 'it''s; DROP'") == []


def test_keyword_inside_comments_is_allowed():
    sql = "SELECT COUNT(*) -- delete everything\nFROM accounts /* DROP TABLE accounts; */"
    assert guard(sql) == []


def test_keyword_hidden_after_comment_is_still_rejected():
    assert "forbidden keyword: DROP" in guard("SELECT COUNT(*) FROM accounts /* ok */ ; DROP TABLE accounts")


def test_whole_word_match_only():
    assert guard("SELECT COUNT(*) AS updated_count, MAX(signup_month) AS created_month FROM accounts") == []


def test_two_statements_are_rejected():
    errors = guard("SELECT 1; DROP TABLE t")
    assert "multiple statements are not allowed" in errors
    assert "forbidden keyword: DROP" in errors


def test_two_selects_are_rejected():
    assert "multiple statements are not allowed" in guard("SELECT COUNT(*) FROM a; SELECT COUNT(*) FROM b")


def test_select_star_on_pii_table_is_rejected():
    errors = guard("SELECT * FROM customers")
    assert "SELECT * is not allowed on PII table 'customers'" in errors


def test_qualified_star_on_pii_join_is_rejected():
    errors = guard("SELECT c.* FROM accounts a JOIN customers c ON c.account_id = a.account_id")
    assert "SELECT * is not allowed on PII table 'customers'" in errors


def test_non_aggregate_pii_query_is_rejected_even_without_aggregate_only():
    errors = guard("SELECT email FROM customers", aggregate_only=False)
    assert "PII table 'customers' can only be read through aggregate queries" in errors


def test_aggregate_on_pii_table_is_allowed():
    assert guard("SELECT COUNT(*) FROM customers") == []


def test_star_on_non_pii_table_is_allowed_when_aggregate():
    assert guard("SELECT COUNT(*), a.* FROM accounts a GROUP BY a.account_id") == []


def test_non_aggregate_query_rejected_when_aggregate_only():
    errors = guard("SELECT account_id FROM accounts")
    assert "query must be aggregate (use COUNT/SUM/AVG/MIN/MAX or GROUP BY)" in errors


def test_non_aggregate_query_allowed_when_aggregate_only_false():
    assert guard("SELECT account_id FROM accounts", aggregate_only=False) == []


def test_group_by_counts_as_aggregate():
    assert guard("SELECT segment FROM accounts GROUP BY segment") == []


def test_limit_above_max_is_rejected():
    errors = guard("SELECT segment FROM accounts GROUP BY segment LIMIT 1000", max_rows=500)
    assert "LIMIT 1000 exceeds max_rows 500" in errors


def test_limit_at_max_and_missing_limit_are_allowed():
    assert guard("SELECT segment FROM accounts GROUP BY segment LIMIT 500", max_rows=500) == []
    assert guard("SELECT segment FROM accounts GROUP BY segment", max_rows=500) == []


@pytest.mark.parametrize("sql", ["", "   ", ";", "-- only a comment"])
def test_empty_query_is_rejected(sql):
    assert guard(sql) == ["query is empty"]


def test_unterminated_string_is_rejected():
    errors = guard("SELECT COUNT(*) FROM accounts WHERE segment = 'abc")
    assert errors == ["query cannot be parsed: unterminated string literal"]


def test_non_string_input_is_rejected():
    assert check_sql(None, [], 500) == ["query is empty"]


def run_cli(*args):
    result = subprocess.run(
        [sys.executable, "scripts/sql_guard.py", *args],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    return result.returncode, result.stdout, result.stderr


def test_cli_allows_aggregate_query():
    code, stdout, stderr = run_cli("--sql", "SELECT COUNT(*) FROM accounts")
    assert code == 0
    assert "Traceback" not in stderr


def test_cli_rejects_mutating_query_with_one_error_per_line():
    code, stdout, stderr = run_cli("--sql", "DELETE FROM accounts")
    assert code == 1
    assert "forbidden keyword: DELETE" in stdout.splitlines()
    assert "Traceback" not in stderr


def test_cli_uses_pii_tables_from_config():
    config = str(REPO_ROOT / "fixtures" / "pm.config.mock.yaml")
    code, stdout, stderr = run_cli("--sql", "SELECT * FROM customers", "--config", config)
    assert code == 1
    assert "SELECT * is not allowed on PII table 'customers'" in stdout
    assert "Traceback" not in stderr


def test_cli_missing_config_is_one_line_error():
    code, stdout, stderr = run_cli("--sql", "SELECT COUNT(*) FROM accounts", "--config", "/nonexistent/pm.yaml")
    assert code == 1
    assert stdout.strip() == "Config not found: /nonexistent/pm.yaml"
    assert "Traceback" not in stderr
