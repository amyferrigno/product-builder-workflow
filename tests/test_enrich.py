"""Test scripts/enrich.py."""

import csv
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from validate_evidence import format_value_pct, validate_evidence

REPO_ROOT = Path(__file__).parent.parent
MOCK_REGISTRY = str(REPO_ROOT / "fixtures" / "registry.mock.yaml")
MOCK_CONFIG = str(REPO_ROOT / "fixtures" / "pm.config.mock.yaml")
SHARE_PARAMS = {"category": "scheduling_conflict", "period_start": "2025-07", "period_end": "2025-12"}


def make_run(tmp_path):
    run_dir = tmp_path / "runs" / "2026-01-15-clean-meeting"
    run_dir.mkdir(parents=True)
    shutil.copy(REPO_ROOT / "fixtures" / "clean-meeting" / "golden" / "02-problem.md", run_dir / "02-problem.md")
    return run_dir


def make_queries_dir(tmp_path):
    queries = tmp_path / "queries"
    shutil.copytree(REPO_ROOT / "connectors" / "queries", queries)
    return queries


def enrich(tmp_path, run_dir, *extra, queries=None, claim="{value_pct}% of {n} tickets", supports="PB-1"):
    queries = queries or make_queries_dir(tmp_path)
    cmd = [
        sys.executable, "scripts/enrich.py", "run", str(run_dir),
        "--provider", "mock_warehouse", "--question", "How common?",
        "--claim", claim, "--supports", supports,
        "--registry", MOCK_REGISTRY, "--config", MOCK_CONFIG,
        "--queries-dir", str(queries), "--cache-dir", str(tmp_path / "cache"),
        *extra,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO_ROOT)
    return result.returncode, result.stdout, result.stderr


def share_args():
    return ["--query-id", "ticket_share_by_category", "--params", json.dumps(SHARE_PARAMS)]


def expected_share_and_total():
    with open(REPO_ROOT / "fixtures" / "mock_warehouse" / "support_tickets.csv", newline="") as f:
        tickets = [t for t in csv.DictReader(f) if "2025-07" <= t["created_month"] <= "2025-12"]
    hits = sum(t["category"] == "scheduling_conflict" for t in tickets)
    return hits / len(tickets), len(tickets)


def dir_hash(path):
    digest = hashlib.sha256()
    for f in sorted(Path(path).rglob("*")):
        if f.is_file():
            digest.update(f.name.encode())
            digest.update(f.read_bytes())
    return digest.hexdigest()


def test_writes_schema_valid_card_with_provider_value(tmp_path):
    run_dir = make_run(tmp_path)
    code, stdout, stderr = enrich(tmp_path, run_dir, *share_args(), "--segment", "all", "--period", "2025-H2")
    assert code == 0, stderr
    assert "Traceback" not in stderr
    result = json.loads(stdout)
    assert result["id"] == "EV-001"
    card = json.loads(Path(result["path"]).read_text())
    assert result["path"].endswith("03-evidence/EV-001.json")

    schema = json.loads((REPO_ROOT / "schemas" / "evidence.schema.json").read_text())
    assert list(Draft202012Validator(schema).iter_errors(card)) == []

    share, total = expected_share_and_total()
    assert abs(card["value"] - share) < 0.005
    assert card["n"] == total
    assert card["confidence"] == "high"
    assert card["source"] == "mock_warehouse"
    assert card["query_id"] == "ticket_share_by_category"
    assert card["metric"] == "ticket_share"
    assert card["supports_problem"] == "PB-1"
    assert card["period"] == "2025-H2"
    assert len(card["query_hash"]) == 64
    assert "synthetic mock warehouse data" in card["caveats"]
    assert card["claim_template"] == "{value_pct}% of {n} tickets"
    assert card["claim"] == f"{format_value_pct(card['value'])}% of {total} tickets"
    assert result["value"] == card["value"] and result["n"] == total
    assert result["claim"] == card["claim"] and result["confidence"] == "high"
    assert card["query_hash"] == hashlib.sha256(
        (REPO_ROOT / "connectors" / "queries" / "ticket_share_by_category.sql").read_text().encode()
    ).hexdigest()


def test_second_card_gets_next_id_and_second_call_uses_cache(tmp_path):
    run_dir = make_run(tmp_path)
    queries = make_queries_dir(tmp_path)
    enrich(tmp_path, run_dir, *share_args(), queries=queries)
    code, stdout, stderr = enrich(tmp_path, run_dir, *share_args(), queries=queries)
    assert code == 0, stderr
    assert json.loads(stdout)["id"] == "EV-002"
    first = json.loads((run_dir / "03-evidence" / "EV-001.json").read_text())
    second = json.loads((run_dir / "03-evidence" / "EV-002.json").read_text())
    assert first["run_at"] == second["run_at"]  # served from cache, not re-run
    assert len(list((tmp_path / "cache").glob("*.json"))) == 1


def test_claim_with_literal_number_is_refused(tmp_path):
    run_dir = make_run(tmp_path)
    code, stdout, stderr = enrich(tmp_path, run_dir, *share_args(), claim="77% of {n} tickets, {value_pct}%")
    assert code == 1
    assert stderr.strip() == "claim template must not contain literal numbers; use {value}, {value_pct} or {n}"
    assert "Traceback" not in stderr
    assert not (run_dir / "03-evidence").exists()
    assert not (tmp_path / "cache").exists()  # refused before the provider ran


def test_bad_templates_are_refused_with_one_line(tmp_path):
    run_dir = make_run(tmp_path)
    cases = {
        "{n} tickets": "claim template must contain {value} or {value_pct}",
        "{value} {nope}": "unknown placeholder '{nope}' in claim template",
        "{value_pct}k tickets": (
            "claim template must not put a magnitude word "
            "(k, m, mn, mm, bn, x, hundred, thousand, million, billion, times) after a number"
        ),
        "{value}% of tickets": "% may follow only {value_pct}",
    }
    queries = make_queries_dir(tmp_path)
    for claim, message in cases.items():
        code, _, stderr = enrich(tmp_path, run_dir, *share_args(), claim=claim, queries=queries)
        assert code == 1
        assert stderr.strip() == message


def test_claim_template_value_and_n_are_filled(tmp_path):
    run_dir = make_run(tmp_path)
    share, total = expected_share_and_total()
    code, stdout, stderr = enrich(tmp_path, run_dir, *share_args(), claim="share {value} ({value_pct} percent) of {n}")
    assert code == 0, stderr
    result = json.loads(stdout)
    assert result["claim"] == f"share {round(share, 2):g} ({format_value_pct(share)} percent) of {total}"
    assert validate_evidence(str(run_dir)) == []


def test_value_pct_is_refused_for_values_above_one(tmp_path):
    run_dir = make_run(tmp_path)
    code, _, stderr = enrich(tmp_path, run_dir, "--query-id", "median_minutes_to_confirm",
                             "--params", '{"segment": "enterprise"}', claim="{value_pct}% of {n}")
    assert code == 1
    assert stderr.strip() == "{value_pct} needs a provider value between 0 and 1"


def test_median_claim_with_value_and_n(tmp_path):
    run_dir = make_run(tmp_path)
    code, stdout, stderr = enrich(tmp_path, run_dir, "--query-id", "median_minutes_to_confirm",
                                  "--params", '{"segment": "enterprise"}',
                                  claim="median {value} minutes over {n} meetings")
    assert code == 0, stderr
    assert json.loads(stdout)["claim"] == "median 74 minutes over 142 meetings"


def test_no_matching_rows_is_reported(tmp_path):
    run_dir = make_run(tmp_path)
    code, _, stderr = enrich(tmp_path, run_dir, "--query-id", "median_minutes_to_confirm",
                             "--params", '{"segment": "nope"}', claim="{value} {n}")
    assert code == 1
    assert stderr.strip() == "provider 'mock_warehouse' refused the request: query returned no rows for these params"


def test_non_numeric_value_does_not_echo_the_cell(tmp_path):
    run_dir = make_run(tmp_path)
    sql = "SELECT COUNT(*) AS n_rows, 'secret@example.invalid' AS email FROM accounts"
    code, _, stderr = enrich(tmp_path, run_dir, "--sql", sql, "--value-field", "email", claim="{value}")
    assert code == 1
    assert stderr.strip() == "provider value is not a number"
    assert "secret" not in stderr


def test_pii_query_cannot_leak_through_value_field(tmp_path):
    run_dir = make_run(tmp_path)
    code, _, stderr = enrich(tmp_path, run_dir, "--sql", "SELECT MAX(email) AS e FROM customers", claim="{value}")
    assert code == 1
    assert "allows only COUNT aggregates" in stderr
    assert "example.invalid" not in stderr


def test_claim_may_use_percentage_form_and_n(tmp_path):
    run_dir = make_run(tmp_path)
    code, _, stderr = enrich(tmp_path, run_dir, *share_args(), claim="{value_pct}% of {n} tickets")
    assert code == 0, stderr


def test_unknown_supports_problem(tmp_path):
    run_dir = make_run(tmp_path)
    code, stdout, stderr = enrich(tmp_path, run_dir, *share_args(), supports="PB-9")
    assert code == 1
    assert stderr.strip() == "unknown problem 'PB-9' (not in 02-problem.md)"
    assert "Traceback" not in stderr


def test_missing_problem_file(tmp_path):
    run_dir = tmp_path / "runs" / "empty"
    run_dir.mkdir(parents=True)
    code, stdout, stderr = enrich(tmp_path, run_dir, *share_args())
    assert code == 1
    assert stderr.strip().startswith("File not found:")
    assert "Traceback" not in stderr


def test_unknown_query_id(tmp_path):
    run_dir = make_run(tmp_path)
    code, stdout, stderr = enrich(tmp_path, run_dir, "--query-id", "nope")
    assert code == 1
    assert stderr.strip() == "unknown query_id 'nope'"


def test_missing_params_are_named(tmp_path):
    run_dir = make_run(tmp_path)
    code, stdout, stderr = enrich(tmp_path, run_dir, "--query-id", "ticket_share_by_category",
                                  "--params", '{"category": "billing"}', claim="{value}")
    assert code == 1
    assert stderr.strip() == "missing params for 'ticket_share_by_category': period_start, period_end"


def test_disabled_provider_is_reported(tmp_path):
    run_dir = make_run(tmp_path)
    code, stdout, stderr = enrich(tmp_path, run_dir, *share_args(),
                                  "--registry", str(REPO_ROOT / "connectors" / "registry.yaml"))
    assert code == 1
    assert stderr.strip() == "unknown provider 'mock_warehouse'"
    assert "Traceback" not in stderr


def test_needs_exactly_one_of_query_id_and_sql(tmp_path):
    run_dir = make_run(tmp_path)
    code, stdout, stderr = enrich(tmp_path, run_dir)
    assert code == 1
    assert stderr.strip() == "give exactly one of --query-id or --sql"


def test_adhoc_sql_is_low_confidence_and_saved_unreviewed(tmp_path):
    run_dir = make_run(tmp_path)
    queries = make_queries_dir(tmp_path)
    sql = "SELECT COUNT(*) AS accounts_total FROM accounts"
    with open(REPO_ROOT / "fixtures" / "mock_warehouse" / "accounts.csv", newline="") as f:
        total = len(list(csv.DictReader(f)))
    code, stdout, stderr = enrich(tmp_path, run_dir, "--sql", sql, queries=queries, claim="{value} accounts")
    assert code == 0, stderr
    card = json.loads(Path(json.loads(stdout)["path"]).read_text())
    assert card["confidence"] == "low"
    assert card["value"] == total
    assert card["query_id"].startswith("adhoc_") and len(card["query_id"]) == len("adhoc_") + 8
    assert card["query_hash"] == hashlib.sha256(sql.encode()).hexdigest()

    library = yaml.safe_load((queries / "index.yaml").read_text())["queries"]
    entry = next(q for q in library if q["id"] == card["query_id"])
    assert entry["status"] == "unreviewed"
    assert entry["provider"] == "mock_warehouse"
    assert (queries / entry["file"]).read_text() == sql
    assert validate_evidence(str(run_dir), str(queries)) == []
    assert len(library) == 4

    # Running it again does not duplicate the library entry.
    enrich(tmp_path, run_dir, "--sql", sql, queries=queries, claim="{value} accounts")
    assert len(yaml.safe_load((queries / "index.yaml").read_text())["queries"]) == 4


def test_adhoc_mutating_sql_is_refused_before_the_provider(tmp_path):
    run_dir = make_run(tmp_path)
    queries = make_queries_dir(tmp_path)
    before = dir_hash(queries)
    code, stdout, stderr = enrich(tmp_path, run_dir, "--sql", "DELETE FROM accounts", queries=queries)
    assert code == 1
    assert "forbidden keyword: DELETE" in stderr.splitlines()
    assert "Traceback" not in stderr
    assert not (tmp_path / "cache").exists()  # the provider was never called
    assert not (run_dir / "03-evidence").exists()
    assert dir_hash(queries) == before


def test_adhoc_pii_select_star_is_refused(tmp_path):
    run_dir = make_run(tmp_path)
    code, stdout, stderr = enrich(tmp_path, run_dir, "--sql", "SELECT * FROM customers")
    assert code == 1
    assert "SELECT * is not allowed on PII table 'customers'" in stderr.splitlines()


def test_repo_query_library_and_registry_are_untouched_by_tests(tmp_path):
    real_queries = REPO_ROOT / "connectors" / "queries"
    before = dir_hash(real_queries)
    run_dir = make_run(tmp_path)
    code, _, stderr = enrich(tmp_path, run_dir, "--sql", "SELECT COUNT(*) AS c FROM accounts", claim="{value} accounts")
    assert code == 0, stderr
    code, _, stderr = enrich(tmp_path, run_dir, *share_args(), queries=real_queries)
    assert code == 0, stderr
    assert dir_hash(real_queries) == before
    registry = yaml.safe_load((REPO_ROOT / "connectors" / "registry.yaml").read_text())
    assert all(p["enabled"] is False for p in registry["providers"])


def cache_files(tmp_path):
    return sorted((tmp_path / "cache").glob("*.json"))


def test_edited_library_query_is_not_served_from_cache(tmp_path):
    run_dir = make_run(tmp_path)
    queries = make_queries_dir(tmp_path)
    code, stdout, stderr = enrich(tmp_path, run_dir, *share_args(), queries=queries)
    assert code == 0, stderr
    first = json.loads(Path(json.loads(stdout)["path"]).read_text())

    sql_file = queries / "ticket_share_by_category.sql"
    sql_file.write_text(sql_file.read_text() + "\n-- edited after the first run\n")
    new_hash = hashlib.sha256(sql_file.read_text().encode()).hexdigest()
    assert new_hash != first["query_hash"]

    code, stdout, stderr = enrich(tmp_path, run_dir, *share_args(), queries=queries)
    assert code == 0, stderr
    second = json.loads(Path(json.loads(stdout)["path"]).read_text())
    assert second["query_hash"] == new_hash
    assert second["run_at"] != first["run_at"]  # re-run, not served from cache
    assert len(cache_files(tmp_path)) == 2


def test_non_numeric_value_is_refused_and_not_cached(tmp_path):
    run_dir = make_run(tmp_path)
    sql = "SELECT MAX(category) AS top_category FROM support_tickets"
    code, _, stderr = enrich(tmp_path, run_dir, "--sql", sql, claim="{value} tickets")
    assert code == 1
    assert stderr.strip() == "provider value is not a number"
    assert cache_files(tmp_path) == []
    assert not (run_dir / "03-evidence").exists()


def test_provider_query_hash_mismatch_is_refused(tmp_path):
    run_dir = make_run(tmp_path)
    stub = tmp_path / "stub_provider.py"
    stub.write_text(
        "import json, sys\n"
        "json.load(sys.stdin)\n"
        "print(json.dumps({'ok': True, 'rows': [{'share': 0.5, 'total_tickets': 10}], 'n': 1,"
        " 'run_at': '2026-01-01T00:00:00+00:00', 'query_hash': 'f' * 64, 'caveats': []}))\n"
    )
    registry = tmp_path / "registry.yaml"
    registry.write_text(yaml.safe_dump({"providers": [{
        "id": "mock_warehouse", "kind": "script", "enabled": True,
        "command": f"python {stub}", "capabilities": ["sql_readonly"],
    }]}))
    code, _, stderr = enrich(tmp_path, run_dir, *share_args(), "--registry", str(registry))
    assert code == 1
    assert stderr.strip() == "provider query_hash does not match the library query (stale or wrong query)"
    assert not (run_dir / "03-evidence").exists()
