"""Test .claude/hooks/guard_readonly_query.py."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
HOOK = ".claude/hooks/guard_readonly_query.py"


def run_hook(payload=None, raw=None, project_dir=REPO_ROOT):
    stdin = raw if raw is not None else json.dumps(payload)
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(project_dir))
    result = subprocess.run(
        [sys.executable, HOOK], input=stdin, capture_output=True, text=True, cwd=REPO_ROOT, env=env,
    )
    return result.returncode, result.stdout, result.stderr


def bash(command):
    return {"tool_name": "Bash", "tool_input": {"command": command}}


def test_blocks_delete_in_bash_sql_argument():
    code, stdout, stderr = run_hook(bash('python scripts/enrich.py run runs/x --sql "DELETE FROM accounts"'))
    assert code == 2
    assert "Blocked: query is not allowed" in stderr
    assert "- forbidden keyword: DELETE" in stderr
    assert "Traceback" not in stderr


def test_blocks_single_quoted_and_equals_forms():
    code, _, stderr = run_hook(bash("python scripts/sql_guard.py --sql 'DROP TABLE accounts'"))
    assert code == 2 and "forbidden keyword: DROP" in stderr
    code, _, stderr = run_hook(bash('python scripts/sql_guard.py --sql="UPDATE accounts SET segment = 1"'))
    assert code == 2 and "forbidden keyword: UPDATE" in stderr


def test_blocks_two_statements_in_bash():
    code, _, stderr = run_hook(bash('x --sql "SELECT COUNT(*) FROM accounts; DROP TABLE accounts"'))
    assert code == 2
    assert "multiple statements are not allowed" in stderr


def test_blocks_mcp_payload_with_drop():
    code, _, stderr = run_hook({"tool_name": "mcp__warehouse__run_query", "tool_input": {"sql": "DROP TABLE x"}})
    assert code == 2
    assert "forbidden keyword: DROP" in stderr


def test_blocks_mcp_query_and_statement_fields():
    for field in ("query", "statement"):
        code, _, stderr = run_hook({"tool_name": "mcp__w__q", "tool_input": {field: "DELETE FROM t"}})
        assert code == 2, field
        assert "forbidden keyword: DELETE" in stderr


def test_allows_select_aggregate_in_bash_and_mcp():
    code, _, stderr = run_hook(bash('x --sql "SELECT COUNT(*) FROM accounts"'))
    assert code == 0 and stderr == ""
    code, _, stderr = run_hook({"tool_name": "mcp__w__q", "tool_input": {"sql": "SELECT segment, COUNT(*) FROM accounts GROUP BY segment"}})
    assert code == 0 and stderr == ""


def test_allows_unrelated_bash_and_tools():
    assert run_hook(bash("ls -la"))[0] == 0
    assert run_hook(bash('echo "DELETE FROM accounts"'))[0] == 0
    assert run_hook({"tool_name": "Write", "tool_input": {"file_path": "a.txt", "sql": "DROP TABLE x"}})[0] == 0


def test_allows_mcp_call_without_sql_fields():
    assert run_hook({"tool_name": "mcp__w__list", "tool_input": {"name": "x"}})[0] == 0


def test_malformed_stdin_exits_zero():
    assert run_hook(raw="not json")[0] == 0
    assert run_hook(raw="")[0] == 0
    assert run_hook(raw="[1, 2]")[0] == 0
    assert run_hook(raw=json.dumps({"tool_name": "Bash", "tool_input": "oops"}))[0] == 0


def test_unbalanced_quotes_do_not_crash():
    code, _, stderr = run_hook(bash('x --sql "DELETE FROM accounts'))
    assert code in (0, 2)
    assert "Traceback" not in stderr


def test_pii_rules_come_from_project_config_inline_list(tmp_path):
    (tmp_path / "pm.config.yaml").write_text("data:\n  max_rows_returned: 50\n  pii_tables: [customers, staff]\n")
    code, _, stderr = run_hook(bash('x --sql "SELECT * FROM customers"'), project_dir=tmp_path)
    assert code == 2 and "SELECT * is not allowed on PII table 'customers'" in stderr
    code, _, stderr = run_hook(bash('x --sql "SELECT segment FROM accounts GROUP BY segment LIMIT 100"'), project_dir=tmp_path)
    assert code == 2 and "LIMIT 100 exceeds max_rows 50" in stderr


def test_pii_rules_come_from_project_config_dash_list(tmp_path):
    (tmp_path / "pm.config.yaml").write_text("data:\n  pii_tables:\n    - customers\njira:\n  mode: dry_run\n")
    code, _, stderr = run_hook(bash('x --sql "SELECT * FROM customers"'), project_dir=tmp_path)
    assert code == 2 and "PII table 'customers'" in stderr


def test_unreadable_config_falls_back_to_defaults(tmp_path):
    code, _, stderr = run_hook(bash('x --sql "SELECT COUNT(*) FROM customers"'), project_dir=tmp_path)
    assert code == 0
    code, _, stderr = run_hook(bash('x --sql "DELETE FROM customers"'), project_dir=tmp_path)
    assert code == 2


def test_hook_agrees_with_guard_on_repo_config():
    code, _, stderr = run_hook(bash('x --sql "SELECT account_id FROM accounts"'))
    assert code == 2
    assert "query must be aggregate" in stderr


def test_mcp_plain_text_query_is_allowed():
    code, _, stderr = run_hook({"tool_name": "mcp__search__find", "tool_input": {"query": "customer scheduling complaints"}})
    assert code == 0 and stderr == ""


def test_mcp_query_starting_with_delete_is_blocked():
    code, _, stderr = run_hook({"tool_name": "mcp__search__find", "tool_input": {"query": "delete from accounts"}})
    assert code == 2 and "forbidden keyword: DELETE" in stderr


def test_mcp_sql_with_leading_comment_is_blocked():
    code, _, stderr = run_hook({"tool_name": "mcp__w__q", "tool_input": {"sql": "/* x */ DROP TABLE t"}})
    assert code == 2 and "forbidden keyword: DROP" in stderr


def test_mcp_lowercase_select_aggregate_is_allowed():
    code, _, stderr = run_hook({"tool_name": "mcp__w__q", "tool_input": {"query": "select count(*) from tickets"}})
    assert code == 0 and stderr == ""


def mcp(tool_input):
    return {"tool_name": "mcp__w__q", "tool_input": tool_input}


def test_mcp_plain_text_starting_with_sql_word_is_allowed():
    for text in ("Update on scheduling complaints", "Select the best themes", "Drop in customer comments", "Delete requests from users"):
        code, _, stderr = run_hook(mcp({"query": text}))
        assert code == 0 and stderr == "", text


def test_mcp_update_statement_is_blocked():
    code, _, stderr = run_hook(mcp({"query": "update accounts set plan = 'x'"}))
    assert code == 2 and "forbidden keyword: UPDATE" in stderr


def test_mcp_nested_params_sql_is_blocked():
    code, _, stderr = run_hook(mcp({"params": {"sql": "drop table t"}}))
    assert code == 2 and "forbidden keyword: DROP" in stderr


def test_mcp_sql_query_key_any_case_is_blocked():
    for key in ("SQL_QUERY", "sql_query", "SQL", "Statement"):
        code, _, stderr = run_hook(mcp({key: "delete from t"}))
        assert code == 2, key
        assert "forbidden keyword: DELETE" in stderr


def test_mcp_nested_plain_text_is_allowed():
    code, _, stderr = run_hook(mcp({"params": {"query": "Update on scheduling complaints"}}))
    assert code == 0 and stderr == ""


def test_mcp_statement_shapes_are_blocked():
    for text in (
        "with x as (select 1) delete from t",
        "INSERT INTO t VALUES (1)",
        "MERGE INTO t USING s ON t.id = s.id",
        "ALTER TABLE t ADD COLUMN c int",
        "CREATE TABLE t (a int)",
        "TRUNCATE TABLE t",
        "truncate t",
        "GRANT SELECT ON t TO bob",
        "REPLACE INTO t VALUES (1)",
        "ATTACH 'x.db' AS other",
        "PRAGMA writable_schema",
        "SELECT COUNT(*) FROM t; DROP TABLE t",
        "-- note\nDROP TABLE t",
    ):
        code, _, stderr = run_hook(mcp({"sql": text}))
        assert code == 2, text
        assert "Traceback" not in stderr


def mcp_sql(sql):
    return {"tool_name": "mcp__warehouse__run_query", "tool_input": {"sql": sql}}


@pytest.mark.parametrize("sql", [
    "UPDATE\"accounts\"SET plan='x'",
    'UPDATE "my table" SET x = 1',
    "UPDATE OR IGNORE accounts SET plan='x'",
    "UPDATE [dbo].[my table] SET x=1",
    "DELETE accounts WHERE id = 1",
    "INSERT accounts VALUES (1)",
    "MERGE accounts USING src ON 1=1",
])
def test_blocks_spelling_variants_of_mutations_in_mcp_payload(sql):
    code, _, stderr = run_hook(mcp_sql(sql))
    assert code == 2
    assert "Blocked: query is not allowed" in stderr
    assert "Traceback" not in stderr


@pytest.mark.parametrize("text", ["Update on scheduling complaints", "Delete requests from users"])
def test_plain_text_search_with_sql_looking_first_word_is_allowed(text):
    code, _, stderr = run_hook(mcp_sql(text))
    assert code == 0
    assert stderr == ""
