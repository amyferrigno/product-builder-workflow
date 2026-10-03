"""Test scripts/providers.py and the mock warehouse provider."""

import csv
import json
import shutil
import sqlite3
import sys
import textwrap
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from providers import ProviderError, run_provider, load_registry, load_config

REPO_ROOT = Path(__file__).parent.parent
MOCK_REGISTRY = str(REPO_ROOT / "fixtures" / "registry.mock.yaml")
MOCK_CONFIG = str(REPO_ROOT / "fixtures" / "pm.config.mock.yaml")
WAREHOUSE = REPO_ROOT / "fixtures" / "mock_warehouse"

SHARE_REQUEST = {
    "question": "How many tickets are scheduling conflicts?",
    "query_id": "ticket_share_by_category",
    "params": {"category": "scheduling_conflict", "period_start": "2025-07", "period_end": "2025-12"},
}


def read_csv(name):
    with open(WAREHOUSE / name, newline="") as f:
        return list(csv.DictReader(f))


def write_script_provider(tmp_path, body, name="provider.py"):
    script = tmp_path / name
    script.write_text(textwrap.dedent(body))
    return script


def write_registry(tmp_path, providers):
    path = tmp_path / "registry.yaml"
    path.write_text(yaml.safe_dump({"providers": providers}))
    return str(path)


def script_entry(provider_id, script, extra_args="", enabled=True):
    return {
        "id": provider_id, "kind": "script", "enabled": enabled,
        "command": f"python {script} {extra_args}".strip(), "capabilities": ["sql_readonly"],
    }


def write_config(tmp_path, **data_overrides):
    config = yaml.safe_load(Path(MOCK_CONFIG).read_text())
    config["data"].update(data_overrides)
    path = tmp_path / "pm.config.yaml"
    path.write_text(yaml.safe_dump(config))
    return str(path)


COUNTING_PROVIDER = """
    import json, sys
    counter = sys.argv[1]
    with open(counter, "a") as f:
        f.write("run\\n")
    json.load(sys.stdin)
    print(json.dumps({"ok": True, "rows": [{"v": 1}], "n": 1, "run_at": "2026-01-01T00:00:00+00:00",
                      "query_hash": "abc", "caveats": []}))
"""

SIMPLE_REQUEST = {"question": "q", "query_id": "any", "params": {}}


def test_happy_path_value_matches_csv(tmp_path):
    output = run_provider(
        "mock_warehouse", SHARE_REQUEST, registry_path=MOCK_REGISTRY,
        config_path=MOCK_CONFIG, cache_dir=str(tmp_path / "cache"),
    )
    tickets = [t for t in read_csv("support_tickets.csv") if "2025-07" <= t["created_month"] <= "2025-12"]
    expected_share = sum(t["category"] == "scheduling_conflict" for t in tickets) / len(tickets)
    assert output["ok"] is True
    assert output["rows"][0]["total_tickets"] == len(tickets)
    assert output["rows"][0]["share"] == pytest.approx(expected_share, abs=0.005)
    assert output["n"] == 1
    assert len(output["query_hash"]) == 64
    assert "cached" not in output


def test_average_messages_matches_csv(tmp_path):
    accounts = {a["account_id"]: a["segment"] for a in read_csv("accounts.csv")}
    done = [int(e["messages_exchanged"]) for e in read_csv("scheduling_events.csv")
            if e["completed"] == "1" and accounts[e["account_id"]] == "smb"]
    request = {"question": "q", "query_id": "avg_messages_per_meeting", "params": {"segment": "smb"}}
    output = run_provider("mock_warehouse", request, MOCK_REGISTRY, MOCK_CONFIG, str(tmp_path / "c"))
    assert output["rows"][0]["avg_messages"] == pytest.approx(sum(done) / len(done), abs=0.01)
    assert output["rows"][0]["n_meetings"] == len(done)


def test_median_minutes_matches_csv(tmp_path):
    accounts = {a["account_id"]: a["segment"] for a in read_csv("accounts.csv")}
    minutes = sorted(int(e["minutes_to_confirm"]) for e in read_csv("scheduling_events.csv")
                     if e["completed"] == "1" and accounts[e["account_id"]] == "mid_market")
    mid = len(minutes) // 2
    expected = minutes[mid] if len(minutes) % 2 else (minutes[mid - 1] + minutes[mid]) / 2
    request = {"question": "q", "query_id": "median_minutes_to_confirm", "params": {"segment": "mid_market"}}
    output = run_provider("mock_warehouse", request, MOCK_REGISTRY, MOCK_CONFIG, str(tmp_path / "c"))
    assert output["rows"][0]["median_minutes"] == expected
    assert output["rows"][0]["n_meetings"] == len(minutes)


def test_second_identical_call_is_served_from_cache(tmp_path):
    cache = str(tmp_path / "cache")
    first, meta1 = run_provider("mock_warehouse", SHARE_REQUEST, MOCK_REGISTRY, MOCK_CONFIG, cache, return_meta=True)
    second, meta2 = run_provider("mock_warehouse", SHARE_REQUEST, MOCK_REGISTRY, MOCK_CONFIG, cache, return_meta=True)
    assert meta1 == {"cached": False}
    assert meta2 == {"cached": True}
    assert second == first  # same run_at proves the output was not recomputed
    assert len(list((tmp_path / "cache").glob("*.json"))) == 1


def test_cache_hit_does_not_rerun_provider(tmp_path):
    counter = tmp_path / "counter.txt"
    script = write_script_provider(tmp_path, COUNTING_PROVIDER)
    registry = write_registry(tmp_path, [script_entry("counting", script, str(counter))])
    cache = str(tmp_path / "cache")
    run_provider("counting", SIMPLE_REQUEST, registry, MOCK_CONFIG, cache)
    run_provider("counting", SIMPLE_REQUEST, registry, MOCK_CONFIG, cache)
    assert counter.read_text().count("run") == 1
    other = dict(SIMPLE_REQUEST, params={"x": 1})
    run_provider("counting", other, registry, MOCK_CONFIG, cache)
    assert counter.read_text().count("run") == 2


def test_expired_ttl_reruns_provider(tmp_path):
    counter = tmp_path / "counter.txt"
    script = write_script_provider(tmp_path, COUNTING_PROVIDER)
    registry = write_registry(tmp_path, [script_entry("counting", script, str(counter))])
    config = write_config(tmp_path, cache_ttl_hours=0)
    cache = str(tmp_path / "cache")
    run_provider("counting", SIMPLE_REQUEST, registry, config, cache)
    _, meta = run_provider("counting", SIMPLE_REQUEST, registry, config, cache, return_meta=True)
    assert meta == {"cached": False}
    assert counter.read_text().count("run") == 2


def test_old_cache_entry_is_not_used(tmp_path):
    counter = tmp_path / "counter.txt"
    script = write_script_provider(tmp_path, COUNTING_PROVIDER)
    registry = write_registry(tmp_path, [script_entry("counting", script, str(counter))])
    cache = tmp_path / "cache"
    run_provider("counting", SIMPLE_REQUEST, registry, MOCK_CONFIG, str(cache))
    (entry_file,) = cache.glob("*.json")
    entry = json.loads(entry_file.read_text())
    entry["cached_at"] = "2000-01-01T00:00:00+00:00"
    entry_file.write_text(json.dumps(entry))
    _, meta = run_provider("counting", SIMPLE_REQUEST, registry, MOCK_CONFIG, str(cache), return_meta=True)
    assert meta == {"cached": False}
    assert counter.read_text().count("run") == 2


def test_unknown_provider_error():
    with pytest.raises(ProviderError) as exc:
        run_provider("nope", SIMPLE_REQUEST, MOCK_REGISTRY, MOCK_CONFIG)
    assert str(exc.value) == "unknown provider 'nope'"


def test_disabled_provider_error():
    with pytest.raises(ProviderError) as exc:
        run_provider("product_analytics", SIMPLE_REQUEST, "connectors/registry.yaml", MOCK_CONFIG)
    assert str(exc.value) == "provider 'product_analytics' is disabled"


def test_mcp_provider_error(tmp_path):
    registry = write_registry(tmp_path, [
        {"id": "wh", "kind": "mcp", "enabled": True, "server": "warehouse", "capabilities": ["sql_readonly"]},
    ])
    with pytest.raises(ProviderError) as exc:
        run_provider("wh", SIMPLE_REQUEST, registry, MOCK_CONFIG)
    assert str(exc.value) == "mcp providers are called by the agent, not by scripts"


def test_invalid_request_error():
    with pytest.raises(ProviderError) as exc:
        run_provider("mock_warehouse", {"question": "q"}, MOCK_REGISTRY, MOCK_CONFIG)
    assert str(exc.value).startswith("request is invalid:")


def test_missing_registry_error(tmp_path):
    with pytest.raises(ProviderError) as exc:
        run_provider("x", SIMPLE_REQUEST, str(tmp_path / "missing.yaml"), MOCK_CONFIG)
    assert str(exc.value).startswith("Registry not found:")


def test_provider_non_zero_exit(tmp_path):
    script = write_script_provider(tmp_path, """
        import sys
        sys.stderr.write("boom happened\\n")
        sys.exit(3)
    """)
    registry = write_registry(tmp_path, [script_entry("bad", script)])
    with pytest.raises(ProviderError) as exc:
        run_provider("bad", SIMPLE_REQUEST, registry, MOCK_CONFIG, str(tmp_path / "c"))
    assert str(exc.value) == "provider 'bad' exited with code 3: boom happened"


def test_provider_invalid_json(tmp_path):
    script = write_script_provider(tmp_path, "print('not json')")
    registry = write_registry(tmp_path, [script_entry("bad", script)])
    with pytest.raises(ProviderError) as exc:
        run_provider("bad", SIMPLE_REQUEST, registry, MOCK_CONFIG, str(tmp_path / "c"))
    assert str(exc.value) == "provider 'bad' returned invalid JSON"


def test_provider_schema_invalid_output(tmp_path):
    script = write_script_provider(tmp_path, """
        import json
        print(json.dumps({"ok": True, "rows": []}))
    """)
    registry = write_registry(tmp_path, [script_entry("bad", script)])
    with pytest.raises(ProviderError) as exc:
        run_provider("bad", SIMPLE_REQUEST, registry, MOCK_CONFIG, str(tmp_path / "c"))
    assert str(exc.value).startswith("provider 'bad' output is invalid:")


def test_provider_ok_false_becomes_error_and_is_not_cached(tmp_path):
    script = write_script_provider(tmp_path, """
        import json
        print(json.dumps({"ok": False, "error": "no access", "rows": [], "n": 0,
                          "run_at": "t", "query_hash": "", "caveats": []}))
    """)
    registry = write_registry(tmp_path, [script_entry("refuser", script)])
    cache = tmp_path / "cache"
    with pytest.raises(ProviderError) as exc:
        run_provider("refuser", SIMPLE_REQUEST, registry, MOCK_CONFIG, str(cache))
    assert str(exc.value) == "provider 'refuser' refused the request: no access"
    assert not list(cache.glob("*.json"))


def test_missing_command_is_one_line_error(tmp_path):
    registry = write_registry(tmp_path, [{
        "id": "ghost", "kind": "script", "enabled": True,
        "command": "/nonexistent/binary --x", "capabilities": ["sql_readonly"],
    }])
    with pytest.raises(ProviderError) as exc:
        run_provider("ghost", SIMPLE_REQUEST, registry, MOCK_CONFIG, str(tmp_path / "c"))
    assert str(exc.value).startswith("provider 'ghost' could not be started:")


def test_rows_are_capped_with_caveat(tmp_path):
    script = write_script_provider(tmp_path, """
        import json
        print(json.dumps({"ok": True, "rows": [{"i": i} for i in range(10)], "n": 10,
                          "run_at": "t", "query_hash": "h", "caveats": ["existing"]}))
    """)
    registry = write_registry(tmp_path, [script_entry("many", script)])
    config = write_config(tmp_path, max_rows_returned=3)
    output = run_provider("many", SIMPLE_REQUEST, registry, config, str(tmp_path / "c"))
    assert output["rows"] == [{"i": 0}, {"i": 1}, {"i": 2}]
    assert output["caveats"] == ["existing", "rows truncated to 3"]


# --- mock warehouse: the guard in front of the provider ---

def adhoc(sql):
    return {"question": "q", "query_id": "adhoc_test", "params": {"__sql": sql}}


@pytest.mark.parametrize("sql,message", [
    ("DELETE FROM accounts", "forbidden keyword: DELETE"),
    ("INSERT INTO accounts VALUES (1, 2, 3, 4)", "forbidden keyword: INSERT"),
    ("UPDATE accounts SET segment = 'x'", "forbidden keyword: UPDATE"),
    ("DROP TABLE accounts", "forbidden keyword: DROP"),
    ("SELECT COUNT(*) FROM accounts; DROP TABLE accounts", "multiple statements are not allowed"),
    ("SELECT * FROM customers", "SELECT * is not allowed on PII table 'customers'"),
    ("SELECT account_id FROM accounts", "query must be aggregate"),
    ("SELECT segment, COUNT(*) FROM accounts GROUP BY segment LIMIT 9999", "LIMIT 9999 exceeds max_rows 500"),
])
def test_mock_warehouse_refuses_unsafe_sql(tmp_path, sql, message):
    with pytest.raises(ProviderError) as exc:
        run_provider("mock_warehouse", adhoc(sql), MOCK_REGISTRY, MOCK_CONFIG, str(tmp_path / "c"))
    assert str(exc.value).startswith("provider 'mock_warehouse' refused the request: query refused by guard:")
    assert message in str(exc.value)


def test_mock_warehouse_runs_adhoc_aggregate(tmp_path):
    output = run_provider(
        "mock_warehouse", adhoc("SELECT COUNT(*) AS c FROM accounts"),
        MOCK_REGISTRY, MOCK_CONFIG, str(tmp_path / "c"),
    )
    assert output["rows"] == [{"c": len(read_csv("accounts.csv"))}]


def test_mock_warehouse_unknown_query_id(tmp_path):
    request = {"question": "q", "query_id": "no_such_query", "params": {}}
    with pytest.raises(ProviderError) as exc:
        run_provider("mock_warehouse", request, MOCK_REGISTRY, MOCK_CONFIG, str(tmp_path / "c"))
    assert str(exc.value) == "provider 'mock_warehouse' refused the request: unknown query_id 'no_such_query'"


def test_mock_warehouse_missing_bind_param(tmp_path):
    request = {"question": "q", "query_id": "avg_messages_per_meeting", "params": {}}
    with pytest.raises(ProviderError) as exc:
        run_provider("mock_warehouse", request, MOCK_REGISTRY, MOCK_CONFIG, str(tmp_path / "c"))
    assert "query failed" in str(exc.value)


def test_mock_warehouse_allows_aggregate_on_pii_table(tmp_path):
    """Aggregates over the PII table are allowed; only row-level reads are refused."""
    sql = "SELECT COUNT(*) AS c FROM customers"
    output = run_provider("mock_warehouse", adhoc(sql), MOCK_REGISTRY, MOCK_CONFIG, str(tmp_path / "c"))
    assert output["rows"][0]["c"] == len(read_csv("customers.csv"))


def test_mock_warehouse_refuses_value_aggregate_on_pii_table(tmp_path):
    sql = "SELECT MAX(email) AS e FROM customers"
    with pytest.raises(ProviderError) as exc:
        run_provider("mock_warehouse", adhoc(sql), MOCK_REGISTRY, MOCK_CONFIG, str(tmp_path / "c"))
    assert "allows only COUNT aggregates" in str(exc.value)


NO_ROWS = "provider 'mock_warehouse' refused the request: query returned no rows for these params"


def test_mock_warehouse_no_matching_rows_is_an_error_not_a_null(tmp_path):
    request = {"question": "q", "query_id": "median_minutes_to_confirm", "params": {"segment": "no_such_segment"}}
    with pytest.raises(ProviderError) as exc:
        run_provider("mock_warehouse", request, MOCK_REGISTRY, MOCK_CONFIG, str(tmp_path / "c"))
    assert str(exc.value) == NO_ROWS


def test_mock_warehouse_empty_result_set_is_an_error(tmp_path):
    sql = "SELECT segment, COUNT(*) AS c FROM accounts WHERE segment = 'nope' GROUP BY segment"
    with pytest.raises(ProviderError) as exc:
        run_provider("mock_warehouse", adhoc(sql), MOCK_REGISTRY, MOCK_CONFIG, str(tmp_path / "c"))
    assert str(exc.value) == NO_ROWS


def test_mock_warehouse_null_aggregate_is_an_error(tmp_path):
    request = {"question": "q", "query_id": "ticket_share_by_category",
               "params": {"category": "billing", "period_start": "2030-01", "period_end": "2030-12"}}
    # COUNT(*) is 0 and the share is NULL here.
    with pytest.raises(ProviderError) as exc:
        run_provider("mock_warehouse", request, MOCK_REGISTRY, MOCK_CONFIG, str(tmp_path / "c"))
    assert str(exc.value) == NO_ROWS


def library():
    return yaml.safe_load((REPO_ROOT / "connectors" / "queries" / "index.yaml").read_text())["queries"]


def test_every_library_query_documents_params_and_an_example_that_returns_a_number(tmp_path):
    for query in library():
        names = [p["name"] for p in query["params"]]
        assert names, query["id"]
        for p in query["params"]:
            assert p["description"], (query["id"], p["name"])
            assert ("format" in p) != ("allowed_values" in p), (query["id"], p["name"])
        example = query["example"]
        assert sorted(example["params"]) == sorted(names), query["id"]
        request = {"question": example["question"], "query_id": query["id"], "params": example["params"]}
        output = run_provider("mock_warehouse", request, MOCK_REGISTRY, MOCK_CONFIG, str(tmp_path / "c"))
        value = output["rows"][0][query["value_field"]]
        assert isinstance(value, (int, float)) and not isinstance(value, bool), query["id"]


def test_allowed_values_match_the_csv_data():
    by_name = {p["name"]: p for q in library() for p in q["params"]}
    categories = {t["category"] for t in read_csv("support_tickets.csv")}
    segments = {a["segment"] for a in read_csv("accounts.csv")}
    assert set(by_name["category"]["allowed_values"]) == categories
    assert set(by_name["segment"]["allowed_values"]) == segments


def test_load_registry_and_config_helpers():
    assert [p["id"] for p in load_registry(MOCK_REGISTRY)["providers"]] == ["mock_warehouse", "mock_anecdotes"]
    assert load_config(MOCK_CONFIG)["data"]["pii_tables"] == ["customers"]
    with pytest.raises(ProviderError) as exc:
        load_config(str(REPO_ROOT / "fixtures" / "registry.mock.yaml"))
    assert "missing the data section" in str(exc.value)


def test_real_registry_has_every_provider_disabled():
    registry = yaml.safe_load((REPO_ROOT / "connectors" / "registry.yaml").read_text())
    assert registry["providers"]
    assert all(p["enabled"] is False for p in registry["providers"])


def test_mock_registry_enables_two_script_providers():
    registry = yaml.safe_load(Path(MOCK_REGISTRY).read_text())
    by_id = {p["id"]: p for p in registry["providers"]}
    assert by_id["mock_warehouse"]["capabilities"] == ["sql_readonly"]
    assert by_id["mock_anecdotes"]["capabilities"] == ["anecdotes"]
    assert all(p["kind"] == "script" and p["enabled"] for p in by_id.values())


def test_library_queries_pass_the_guard():
    from sql_guard import check_sql
    queries_dir = REPO_ROOT / "connectors" / "queries"
    library = yaml.safe_load((queries_dir / "index.yaml").read_text())["queries"]
    assert len(library) >= 3
    for query in library:
        sql = (queries_dir / query["file"]).read_text()
        assert check_sql(sql, ["customers"], 500) == [], query["id"]


# --- The database enforces read-only and PII rules (sqlite authorizer) ---
sys.path.insert(0, str(REPO_ROOT / "connectors" / "providers"))
import mock_warehouse  # noqa: E402

NOT_AUTHORIZED = "query not authorized: reads a PII column or is not read-only"
PERSONAL_VALUES = ("example.invalid", "Test Person", "+00")

PII_BYPASS_SQL = [
    'SELECT MAX(email) FROM"customers"',
    "SELECT MAX(full_name), MAX(email), MAX(phone), COUNT(*) FROM`customers`",
    'SELECT MAX(email) FROM customers"c"',
    'SELECT MAX(c.email) FROM accounts a JOIN"customers"c ON c.account_id=a.account_id',
    "SELECT COUNT(CASE WHEN email LIKE 'person1@%' THEN 1 END) FROM customers",
    "SELECT COUNT(*) FROM customers WHERE customer_id='C001' AND substr(email,1,1)='p'",
    "SELECT COUNT(*) FROM support_tickets t JOIN customers c ON c.customer_id='C002' "
    "WHERE t.rowid <= unicode(substr(c.email,7,1))",
    "SELECT COUNT(*) FROM customers ORDER BY email",
    "SELECT MAX(sql) FROM sqlite_master",
    "SELECT COUNT(*) AS [a'], (SELECT group_concat(email) FROM customers) AS [b'] FROM accounts",
    "SELECT email, COUNT(*) OVER () FROM customers",
]
MUTATION_SQL = [
    "UPDATE\"accounts\"SET plan='x'",
    "WITH t AS (SELECT COUNT(*) FROM accounts) UPDATE\"accounts\"SET plan='x'",
    "DELETE FROM accounts",
    "DROP TABLE accounts",
    "INSERT INTO accounts VALUES ('x','y','z','w')",
    "ATTACH DATABASE ':memory:' AS x",
    "PRAGMA table_info(customers)",
]
COUNT_ACCOUNTS = "SELECT COUNT(*) AS c FROM accounts"


def assert_nothing_personal(text):
    for value in PERSONAL_VALUES:
        assert value not in text, value


def assert_cache_has_nothing_personal(cache_dir):
    for f in Path(cache_dir).rglob("*"):
        if f.is_file():
            assert_nothing_personal(f.read_text())


def accounts_count_via_provider(cache_dir):
    output = run_provider("mock_warehouse", adhoc(COUNT_ACCOUNTS), MOCK_REGISTRY, MOCK_CONFIG, str(cache_dir))
    return output["rows"][0]["c"]


@pytest.mark.parametrize("sql", PII_BYPASS_SQL)
def test_provider_refuses_pii_bypass_and_leaks_nothing(tmp_path, sql):
    cache = tmp_path / "cache"
    with pytest.raises(ProviderError) as exc:
        run_provider("mock_warehouse", adhoc(sql), MOCK_REGISTRY, MOCK_CONFIG, str(cache))
    assert str(exc.value).startswith("provider 'mock_warehouse' refused the request: ")
    assert_nothing_personal(str(exc.value))
    assert_cache_has_nothing_personal(cache)
    assert not list(cache.glob("*.json"))


@pytest.fixture
def bypass_guard(monkeypatch):
    """Run the provider module's query code with the text guard switched off."""
    monkeypatch.setenv("PM_CONFIG", MOCK_CONFIG)
    monkeypatch.setattr(mock_warehouse, "check_sql", lambda *args, **kwargs: [])


@pytest.mark.parametrize("sql", PII_BYPASS_SQL)
def test_authorizer_refuses_pii_bypass_when_text_guard_misses(bypass_guard, sql):
    out = mock_warehouse.build_output(adhoc(sql))
    assert out["ok"] is False
    assert out["rows"] == []
    assert_nothing_personal(json.dumps(out["error"]))
    assert out["error"] == NOT_AUTHORIZED or out["error"].startswith("query failed: ")


@pytest.mark.parametrize("sql", [s for s in PII_BYPASS_SQL if "customers\"c\"" not in s])
def test_authorizer_message_is_exact_for_pii_reads(bypass_guard, sql):
    assert mock_warehouse.build_output(adhoc(sql))["error"] == NOT_AUTHORIZED


@pytest.mark.parametrize("sql", MUTATION_SQL)
def test_authorizer_refuses_mutations_when_text_guard_misses(bypass_guard, sql):
    out = mock_warehouse.build_output(adhoc(sql))
    assert out["ok"] is False
    assert out["error"] == NOT_AUTHORIZED
    assert mock_warehouse.build_output(adhoc(COUNT_ACCOUNTS))["rows"] == [{"c": len(read_csv("accounts.csv"))}]


@pytest.mark.parametrize("sql", MUTATION_SQL)
def test_provider_refuses_mutations_and_data_is_unchanged(tmp_path, sql):
    cache = tmp_path / "cache"
    with pytest.raises(ProviderError) as exc:
        run_provider("mock_warehouse", adhoc(sql), MOCK_REGISTRY, MOCK_CONFIG, str(cache))
    assert str(exc.value).startswith("provider 'mock_warehouse' refused the request: ")
    assert not list(cache.glob("*.json"))
    assert accounts_count_via_provider(cache) == len(read_csv("accounts.csv"))


@pytest.mark.parametrize("sql", MUTATION_SQL)
def test_mutation_on_one_connection_leaves_the_rows_unchanged(sql):
    conn = mock_warehouse.load_warehouse()
    conn.set_authorizer(mock_warehouse.make_authorizer(["customers"]))
    with pytest.raises(sqlite3.DatabaseError, match="not authorized"):
        conn.execute(sql).fetchall()
    assert conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] == len(read_csv("accounts.csv"))
    conn.close()


@pytest.mark.parametrize("function", [
    "load_extension", "readfile", "writefile", "edit", "fts3_tokenizer", "pragma_table_info", "LOAD_EXTENSION",
])
def test_authorizer_denies_dangerous_functions(function):
    authorizer = mock_warehouse.make_authorizer(["customers"])
    assert authorizer(sqlite3.SQLITE_FUNCTION, None, function, None, None) == sqlite3.SQLITE_DENY
    assert authorizer(sqlite3.SQLITE_FUNCTION, None, "count", None, None) == sqlite3.SQLITE_OK


def test_dangerous_function_call_is_refused_end_to_end(bypass_guard):
    out = mock_warehouse.build_output(adhoc("SELECT COUNT(*), load_extension('x') FROM accounts"))
    assert out["ok"] is False
    assert out["error"] in (NOT_AUTHORIZED, "query failed: no such function: load_extension")


def test_authorizer_denies_a_non_numeric_cell_when_the_query_names_a_pii_table(bypass_guard, monkeypatch):
    monkeypatch.setattr(mock_warehouse, "make_authorizer", lambda pii_tables: (lambda *args: sqlite3.SQLITE_OK))
    out = mock_warehouse.build_output(adhoc("SELECT MAX(email) FROM customers"))
    assert out["ok"] is False
    assert out["error"] == NOT_AUTHORIZED
    assert_nothing_personal(json.dumps(out["error"]))


def test_row_count_of_a_pii_table_is_allowed(tmp_path):
    output = run_provider(
        "mock_warehouse", adhoc("SELECT COUNT(*) FROM customers"),
        MOCK_REGISTRY, MOCK_CONFIG, str(tmp_path / "c"),
    )
    assert list(output["rows"][0].values()) == [80]


def test_library_queries_return_the_same_values_under_the_authorizer(tmp_path):
    cache = str(tmp_path / "c")
    share = run_provider("mock_warehouse", SHARE_REQUEST, MOCK_REGISTRY, MOCK_CONFIG, cache)
    tickets = [t for t in read_csv("support_tickets.csv") if "2025-07" <= t["created_month"] <= "2025-12"]
    hits = sum(t["category"] == "scheduling_conflict" for t in tickets)
    assert share["rows"][0]["share"] == pytest.approx(hits / len(tickets))
    assert share["rows"][0]["total_tickets"] == len(tickets)
    avg = run_provider(
        "mock_warehouse",
        {"question": "q", "query_id": "avg_messages_per_meeting", "params": {"segment": "smb"}},
        MOCK_REGISTRY, MOCK_CONFIG, cache,
    )
    assert avg["rows"][0]["n_meetings"] > 0 and avg["rows"][0]["avg_messages"] > 0
    median = run_provider(
        "mock_warehouse",
        {"question": "q", "query_id": "median_minutes_to_confirm", "params": {"segment": "mid_market"}},
        MOCK_REGISTRY, MOCK_CONFIG, cache,
    )
    assert median["rows"][0]["n_meetings"] > 0 and median["rows"][0]["median_minutes"] > 0


def test_sqlite_reports_an_empty_column_name_for_count_star():
    """The authorizer relies on this: COUNT(*) reads no named column, COUNT(col) does."""
    seen = []

    def spy(action, arg1, arg2, db_name, trigger):
        if action == sqlite3.SQLITE_READ:
            seen.append((arg1, arg2))
        return sqlite3.SQLITE_OK

    conn = mock_warehouse.load_warehouse()
    conn.set_authorizer(spy)
    conn.execute("SELECT COUNT(*) FROM customers").fetchall()
    assert seen == [("customers", "")]
    seen.clear()
    conn.execute("SELECT COUNT(email) FROM customers").fetchall()
    assert seen == [("customers", "email")]
    conn.close()


# --- Cache key includes the query text ---
def make_queries_copy(tmp_path):
    queries = tmp_path / "queries"
    shutil.copytree(REPO_ROOT / "connectors" / "queries", queries)
    return queries


def test_cache_salt_changes_the_cache_key(tmp_path):
    cache = tmp_path / "cache"
    for salt in ("aaa", "bbb"):
        run_provider("mock_warehouse", SHARE_REQUEST, MOCK_REGISTRY, MOCK_CONFIG, str(cache), cache_salt=salt)
    assert len(list(cache.glob("*.json"))) == 2
    _, meta = run_provider(
        "mock_warehouse", SHARE_REQUEST, MOCK_REGISTRY, MOCK_CONFIG, str(cache),
        return_meta=True, cache_salt="aaa",
    )
    assert meta == {"cached": True}


def test_cache_filter_false_writes_no_cache_file(tmp_path):
    cache = tmp_path / "cache"
    run_provider(
        "mock_warehouse", SHARE_REQUEST, MOCK_REGISTRY, MOCK_CONFIG, str(cache), cache_filter=lambda out: False,
    )
    assert not list(cache.glob("*.json"))
