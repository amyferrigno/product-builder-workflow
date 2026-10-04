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
    assert "query must be aggregate (use at least one COUNT/SUM/AVG/MIN/MAX call)" in errors


def test_non_aggregate_query_allowed_when_aggregate_only_false():
    assert guard("SELECT account_id FROM accounts", aggregate_only=False) == []


def test_group_by_alone_is_not_aggregate():
    errors = guard("SELECT event_id FROM scheduling_events GROUP BY event_id")
    assert "query must be aggregate (use at least one COUNT/SUM/AVG/MIN/MAX call)" in errors


def test_group_by_with_count_is_allowed():
    assert guard("SELECT segment, COUNT(*) FROM accounts GROUP BY segment") == []


def test_limit_above_max_is_rejected():
    errors = guard("SELECT segment, COUNT(*) FROM accounts GROUP BY segment LIMIT 1000", max_rows=500)
    assert "LIMIT 1000 exceeds max_rows 500" in errors


def test_limit_at_max_and_missing_limit_are_allowed():
    assert guard("SELECT segment, COUNT(*) FROM accounts GROUP BY segment LIMIT 500", max_rows=500) == []
    assert guard("SELECT segment, COUNT(*) FROM accounts GROUP BY segment", max_rows=500) == []


BRACKET_ERR = ["bracket identifiers are not allowed"]


@pytest.mark.parametrize("sql", [
    "WITH t AS (SELECT COUNT(*) AS [a'] FROM accounts) DELETE FROM accounts "
    "WHERE 1 IN (SELECT [a'] FROM t) OR 1=1",
    "SELECT COUNT(*) AS [a'], (SELECT group_concat(email) FROM customers) AS [b'] FROM accounts",
    "SELECT COUNT(*) AS [x] FROM accounts",
])
def test_bracket_identifiers_are_rejected(sql):
    assert guard(sql) == BRACKET_ERR


def test_bracket_inside_string_or_comment_is_allowed():
    assert guard("SELECT COUNT(*) FROM accounts WHERE segment = '[x]' -- [y]") == []


def test_backtick_identifier_with_quote_cannot_hide_keywords():
    sql = (
        "WITH t AS (SELECT COUNT(*) AS `a'` FROM accounts) "
        "DELETE FROM accounts WHERE 1 IN (SELECT `a'` FROM t) OR 1=1"
    )
    assert "forbidden keyword: DELETE" in guard(sql)


def test_double_quote_identifier_with_quote_cannot_hide_keywords():
    sql = (
        'WITH t AS (SELECT COUNT(*) AS "a\'" FROM accounts) '
        'DELETE FROM accounts WHERE 1 IN (SELECT "a\'" FROM t) OR 1=1'
    )
    assert "forbidden keyword: DELETE" in guard(sql)


def test_doubled_quote_inside_identifier_is_handled():
    assert guard('SELECT COUNT(*) AS "a""b" FROM accounts') == []


@pytest.mark.parametrize("sql", [
    "SELECT ALL *, COUNT(*) OVER () FROM customers",
    "SELECT email, COUNT(*) OVER () FROM customers",
    "SELECT email, full_name, phone FROM customers GROUP BY email",
    "SELECT MAX(email) FROM customers",
    "SELECT group_concat(email), COUNT(*) FROM customers",
    "SELECT COUNT(*), email FROM customers",
    "SELECT COUNT(*) + 1 FROM customers",
    "SELECT COUNT(*) FROM (SELECT email FROM customers)",
    "SELECT COUNT(*) FROM accounts WHERE account_id IN (SELECT MIN(email) FROM customers)",
])
def test_pii_decoy_queries_are_rejected(sql):
    assert guard(sql) != []


def test_pii_count_forms_are_allowed():
    assert guard("SELECT COUNT(*) FROM customers") == []
    assert guard("SELECT COUNT(DISTINCT account_id) AS n FROM customers") == []
    assert guard("SELECT COUNT(email) n, COUNT(*) FROM customers WHERE phone IS NOT NULL") == []


def test_pii_join_with_group_by_is_rejected_under_strict_rule():
    sql = ("SELECT accounts.segment, COUNT(*) FROM accounts "
           "JOIN customers ON customers.account_id = accounts.account_id GROUP BY accounts.segment")
    errors = guard(sql)
    assert any("GROUP BY" in e for e in errors)


def test_window_functions_rejected_under_aggregate_only():
    sql = "SELECT COUNT(*), ROW_NUMBER() OVER (ORDER BY account_id) FROM accounts"
    assert "window functions are not allowed" in guard(sql)
    assert guard(sql, aggregate_only=False) == []


def test_window_call_does_not_count_as_aggregate():
    errors = guard("SELECT COUNT(*) OVER () FROM accounts")
    assert "query must be aggregate (use at least one COUNT/SUM/AVG/MIN/MAX call)" in errors


def test_group_concat_and_string_agg_rejected_under_aggregate_only():
    msg = "group_concat and string_agg are not allowed (they return row-level text)"
    assert msg in guard("SELECT COUNT(*), group_concat(segment) FROM accounts")
    assert msg in guard("SELECT COUNT(*), string_agg(segment, ',') FROM accounts")
    assert msg not in guard("SELECT group_concat(segment) FROM accounts", aggregate_only=False)


LIMIT_MSG = "LIMIT must be an integer, optionally followed by OFFSET and an integer"


@pytest.mark.parametrize("limit", ["250+251", "0, 99999", "(99999)", "-1", ":n", "5 OFFSET (1)"])
def test_odd_limit_forms_are_rejected(limit):
    assert LIMIT_MSG in guard(f"SELECT segment, COUNT(*) FROM accounts GROUP BY segment LIMIT {limit}")


def test_limit_offset_forms():
    base = "SELECT segment, COUNT(*) FROM accounts GROUP BY segment"
    assert guard(f"{base} LIMIT 10 OFFSET 5") == []
    assert guard(f"{base} LIMIT 10 OFFSET 5;") == []
    assert "LIMIT 501 exceeds max_rows 500" in guard(f"{base} LIMIT 501 OFFSET 5")
    assert guard("SELECT COUNT(*) FROM (SELECT segment FROM accounts LIMIT 10) UNION SELECT 1") == []


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


@pytest.mark.parametrize("sql", [
    'SELECT MAX(email) FROM"customers"',
    "SELECT MAX(full_name), MAX(email), MAX(phone), COUNT(*) FROM`customers`",
    'SELECT MAX(email) FROM customers"c"',
    'SELECT MAX(c.email) FROM accounts a JOIN"customers"c ON c.account_id=a.account_id',
])
def test_quoted_identifier_does_not_fuse_with_neighbours(sql):
    errors = guard(sql)
    assert "PII table 'customers' allows only COUNT aggregates (MAX is not allowed)" in errors


@pytest.mark.parametrize("quote", ['"', "`"])
def test_cte_followed_by_fused_update_is_rejected(quote):
    sql = f"WITH t AS (SELECT COUNT(*) FROM accounts) UPDATE{quote}accounts{quote}SET plan='x'"
    assert guard(sql) == ["forbidden keyword: UPDATE"]


def test_quoted_digit_limit_is_rejected():
    errors = guard('SELECT COUNT(*) FROM accounts LIMIT"5"')
    assert errors == ["LIMIT must be an integer, optionally followed by OFFSET and an integer"]


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
