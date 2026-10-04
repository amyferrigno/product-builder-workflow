"""Test the live path of scripts/jira_publish.py against the in-memory fake Jira (no network)."""

import json
import subprocess
import sys
import urllib.request
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).parent))
import jira_client  # noqa: E402
import jira_publish  # noqa: E402
from fake_jira import FakeJira  # noqa: E402
from jira_client import JiraClient  # noqa: E402
from check_approval import approval_status  # noqa: E402
from tickets_helpers import make_tickets_run  # noqa: E402
from ux_gate_helpers import write_state  # noqa: E402
from ux_hash import ux_hash  # noqa: E402

SITE = "https://example.atlassian.net"
TOKEN = "tok-DISTINCTIVE-9f8e7d6c"
EMAIL = "someone@example.com"


def approved_run(tmp_path, ai=False):
    run = make_tickets_run(tmp_path, ai=ai)
    write_state(run)
    result = subprocess.run(
        [sys.executable, "scripts/approve.py", str(run), "tickets",
         "--decisions-file", str(run / "decisions.test.md")],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stderr
    return run


def write_config(tmp_path, mode="publish", site=SITE, project_key="DEMO", **extra):
    jira = {"mode": mode, "site": site, "project_key": project_key, "default_labels": ["agentic-pm"]}
    jira.update(extra)
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump({"jira": jira}))
    return path


def make_client(fake, sleeps=None):
    sleeps = [] if sleeps is None else sleeps
    return JiraClient(SITE, EMAIL, TOKEN, transport=fake.transport, sleep=sleeps.append,
                      min_interval=0, max_retries=5)


def manifest_of(run):
    return json.loads((run / "tickets.manifest.json").read_text())


def all_tickets(manifest):
    """Epics first, then children in manifest order (the publish order)."""
    out = list(manifest["epics"])
    for epic in manifest["epics"]:
        out.extend(epic["children"])
    return out


def issue_posts(fake):
    return [r for r in fake.requests if r.method == "POST" and r.path == "/rest/api/3/issue"]


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("JIRA_EMAIL", EMAIL)
    monkeypatch.setenv("JIRA_API_TOKEN", TOKEN)


# --- no approval, no request ---

def test_no_approval_sends_nothing(tmp_path):
    run = make_tickets_run(tmp_path)
    fake = FakeJira()
    with pytest.raises(ValueError, match="approval is not valid"):
        jira_publish.publish(str(run), str(write_config(tmp_path)), client=make_client(fake))
    assert len(fake.requests) == 0


def test_stale_approval_sends_nothing(tmp_path):
    run = approved_run(tmp_path)
    m = manifest_of(run)
    m["epics"][0]["children"][0]["priority"] = "Low"
    (run / "tickets.manifest.json").write_text(json.dumps(m))
    fake = FakeJira()
    with pytest.raises(ValueError, match="stale"):
        jira_publish.publish(str(run), str(write_config(tmp_path)), client=make_client(fake))
    assert len(fake.requests) == 0


def test_invalid_approval_file_sends_nothing(tmp_path):
    run = approved_run(tmp_path)
    (run / "approvals" / "tickets.approved").write_text("{not json")
    fake = FakeJira()
    with pytest.raises(ValueError, match="invalid"):
        jira_publish.publish(str(run), str(write_config(tmp_path)), client=make_client(fake))
    assert len(fake.requests) == 0


def test_invalid_manifest_sends_nothing(tmp_path, monkeypatch):
    run = approved_run(tmp_path)
    m = manifest_of(run)
    m["epics"][0]["children"][0]["jira_key"] = "bad-key"
    (run / "tickets.manifest.json").write_text(json.dumps(m))
    monkeypatch.setattr(jira_publish, "approval_status", lambda run_dir, kind: (True, "ok"))
    fake = FakeJira()
    with pytest.raises(ValueError, match="T-001"):
        jira_publish.publish(str(run), str(write_config(tmp_path)), client=make_client(fake))
    assert len(fake.requests) == 0


# --- happy path and idempotency ---

def test_first_publish_creates_everything_epics_first_with_parents(tmp_path):
    run = approved_run(tmp_path)
    fake = FakeJira()
    counts = jira_publish.publish(str(run), str(write_config(tmp_path)), client=make_client(fake))
    manifest = manifest_of(run)
    tickets = all_tickets(manifest)
    assert counts == {"created": len(tickets), "updated": 0}
    assert len(fake.issues) == len(tickets)
    posts = issue_posts(fake)
    n_epics = len(manifest["epics"])
    kinds = [p.body["fields"]["issuetype"]["name"] for p in posts]
    assert kinds[:n_epics] == ["Epic"] * n_epics
    assert "Epic" not in kinds[n_epics:]
    for post in posts[:n_epics]:
        assert "parent" not in post.body["fields"]
    for epic in manifest["epics"]:
        for child in epic["children"]:
            fields = fake.issues[child["jira_key"]]
            assert fields["parent"] == {"key": epic["jira_key"]}
            assert fields["project"] == {"key": "DEMO"}
            assert set(child["labels"]) <= set(fields["labels"])


def test_description_is_adf_and_no_forbidden_fields(tmp_path):
    run = approved_run(tmp_path)
    fake = FakeJira()
    jira_publish.publish(str(run), str(write_config(tmp_path)), client=make_client(fake))
    for post in issue_posts(fake):
        description = post.body["fields"]["description"]
        assert description["type"] == "doc" and description["version"] == 1 and description["content"]
    flat = json.dumps([r.body for r in fake.requests]).lower()
    assert "sub-task" not in flat and "subtask" not in flat
    assert "story point" not in flat and "story_point" not in flat and "storypoint" not in flat


def test_issue_types_come_from_config(tmp_path):
    run = approved_run(tmp_path)
    fake = FakeJira()
    config = write_config(tmp_path, issue_types={"Spike": "Investigation"})
    jira_publish.publish(str(run), str(config), client=make_client(fake))
    kinds = {p.body["fields"]["issuetype"]["name"] for p in issue_posts(fake)}
    assert kinds == {"Epic", "Story", "Task", "Investigation"}


def test_default_issue_types_map_spike_to_task(tmp_path):
    run = approved_run(tmp_path)
    fake = FakeJira()
    jira_publish.publish(str(run), str(write_config(tmp_path)), client=make_client(fake))
    kinds = {p.body["fields"]["issuetype"]["name"] for p in issue_posts(fake)}
    assert kinds == {"Epic", "Story", "Task"}


def test_second_publish_creates_nothing_and_updates_all(tmp_path):
    run = approved_run(tmp_path)
    fake = FakeJira()
    config = write_config(tmp_path)
    jira_publish.publish(str(run), str(config), client=make_client(fake))
    total = len(all_tickets(manifest_of(run)))
    before_posts = len(issue_posts(fake))
    counts = jira_publish.publish(str(run), str(config), client=make_client(fake))
    assert counts == {"created": 0, "updated": total}
    assert len(issue_posts(fake)) == before_posts
    assert len(fake.issues) == total
    puts = [r for r in fake.requests if r.method == "PUT"]
    assert len(puts) == total
    for put in puts:
        assert "project" not in put.body["fields"] and "issuetype" not in put.body["fields"]
    log = json.loads((run / "tickets.published.json").read_text())
    assert len(log) == 2 * total
    assert [e["action"] for e in log[:total]] == ["created"] * total
    assert [e["action"] for e in log[total:]] == ["updated"] * total
    assert log[0]["url"] == f"{SITE}/browse/{log[0]['key']}"
    assert set(log[0]) == {"ticket_id", "key", "action", "url"}


# --- resume, adopt, duplicates ---

def test_failure_midway_keeps_earlier_keys_and_rerun_creates_only_the_rest(tmp_path):
    run = approved_run(tmp_path)
    config = write_config(tmp_path)
    fake = FakeJira()
    total = len(all_tickets(manifest_of(run)))
    fake.fail_on_request(6, 400)  # tickets 1 and 2 use requests 1-4; ticket 3 searches (5), create fails (6)
    with pytest.raises(jira_publish.PublishFailed) as exc:
        jira_publish.publish(str(run), str(config), client=make_client(fake))
    third = all_tickets(manifest_of(run))[2]["id"]
    message = str(exc.value)
    assert f"FAILED at {third}" in message and "2 published before the failure; rerun to resume" in message
    tickets = all_tickets(manifest_of(run))
    assert [t["jira_key"] is not None for t in tickets] == [True, True] + [False] * (total - 2)
    state = json.loads((run / "state.json").read_text())
    assert set(state["jira_keys"]) == {tickets[0]["id"], tickets[1]["id"]}
    assert state["stage"] != "done"
    assert len(json.loads((run / "tickets.published.json").read_text())) == 2

    counts = jira_publish.publish(str(run), str(config), client=make_client(fake))
    assert counts == {"created": total - 2, "updated": 2}
    assert len(fake.issues) == total
    assert len(set(fake.created_keys())) == total


def test_failure_via_cli_exits_one_with_both_lines(tmp_path, monkeypatch, env, capsys):
    run = approved_run(tmp_path)
    config = write_config(tmp_path)
    fake = FakeJira()
    fake.fail_on_request(2, 400)
    monkeypatch.setattr(jira_client, "default_transport", fake.transport)
    monkeypatch.setattr(sys, "argv", ["jira_publish.py", str(run), "--config", str(config), "--publish"])
    with pytest.raises(SystemExit) as exc:
        jira_publish.main()
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "FAILED at EPIC-01" in err and "0 published before the failure; rerun to resume" in err


def test_lost_manifest_key_is_adopted_not_duplicated(tmp_path):
    run = approved_run(tmp_path)
    config = write_config(tmp_path)
    fake = FakeJira()
    jira_publish.publish(str(run), str(config), client=make_client(fake))
    total = len(fake.issues)
    manifest = manifest_of(run)
    lost = manifest["epics"][0]["children"][0]
    key = lost["jira_key"]
    lost["jira_key"] = None
    (run / "tickets.manifest.json").write_text(json.dumps(manifest))
    counts = jira_publish.publish(str(run), str(config), client=make_client(fake))
    assert counts == {"created": 0, "updated": total}
    assert len(fake.issues) == total
    assert manifest_of(run)["epics"][0]["children"][0]["jira_key"] == key


def test_preexisting_labelled_issue_is_adopted(tmp_path):
    run = approved_run(tmp_path)
    manifest = manifest_of(run)
    slug = manifest["prd_slug"]
    fake = FakeJira()
    seeded = fake.seed_issue({"summary": "old", "labels": [f"ext-{slug}-t-001"]})
    jira_publish.publish(str(run), str(write_config(tmp_path)), client=make_client(fake))
    assert manifest_of(run)["epics"][0]["children"][0]["jira_key"] == seeded
    assert len(fake.issues) == len(all_tickets(manifest))  # the seeded issue was reused, not duplicated


def test_two_issues_with_same_label_stop_the_publish(tmp_path):
    run = approved_run(tmp_path)
    slug = manifest_of(run)["prd_slug"]
    label = f"ext-{slug}-t-001"
    fake = FakeJira()
    a = fake.seed_issue({"summary": "a", "labels": [label]})
    b = fake.seed_issue({"summary": "b", "labels": [label]})
    with pytest.raises(jira_publish.PublishFailed) as exc:
        jira_publish.publish(str(run), str(write_config(tmp_path)), client=make_client(fake))
    assert f"duplicate idempotency label {label}: {a}, {b}" in str(exc.value)
    assert "FAILED at T-001" in str(exc.value)


# --- retries ---

def test_429_with_retry_after_and_500_are_retried(tmp_path):
    run = approved_run(tmp_path)
    fake = FakeJira()
    fake.fail_on_request(1, 429, {"Retry-After": "2"})
    fake.fail_on_request(4, 500)
    sleeps = []
    counts = jira_publish.publish(str(run), str(write_config(tmp_path)), client=make_client(fake, sleeps))
    total = len(all_tickets(manifest_of(run)))
    assert counts["created"] == total and len(fake.issues) == total
    assert 2.0 in sleeps and len(sleeps) >= 2


def test_400_fails_at_once_without_retry(tmp_path):
    run = approved_run(tmp_path)
    fake = FakeJira()
    sleeps = []
    fake.fail_on_request(1, 400)
    with pytest.raises(jira_publish.PublishFailed):
        jira_publish.publish(str(run), str(write_config(tmp_path)), client=make_client(fake, sleeps))
    assert len(fake.requests) == 1 and sleeps == []


# --- secrets ---

def test_token_never_printed_or_written(tmp_path, monkeypatch, env, capsys):
    run = approved_run(tmp_path)
    config = write_config(tmp_path)
    fake = FakeJira()
    fake.fail_on_request(8, 400)  # one failure first so the error path is covered too
    monkeypatch.setattr(jira_client, "default_transport", fake.transport)
    argv = ["jira_publish.py", str(run), "--config", str(config), "--publish"]
    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(SystemExit):
        jira_publish.main()
    jira_publish.main()
    captured = capsys.readouterr()
    for text in (captured.out, captured.err):
        assert TOKEN not in text and EMAIL not in text
    files = [p for p in tmp_path.rglob("*") if p.is_file()]
    assert files
    for path in files:
        assert TOKEN.encode() not in path.read_bytes(), path


# --- write-back ---

def test_keys_written_to_manifest_state_traceability_and_approval_survives(tmp_path):
    run = approved_run(tmp_path)
    prd_before = (run / "prd.md").read_bytes()
    ux_before = ux_hash(run)
    fake = FakeJira()
    jira_publish.publish(str(run), str(write_config(tmp_path)), client=make_client(fake))
    tickets = all_tickets(manifest_of(run))
    state = json.loads((run / "state.json").read_text())
    trace = (run / "traceability.md").read_text()
    assert all(t["jira_key"] for t in tickets)
    assert state["jira_keys"] == {t["id"]: t["jira_key"] for t in tickets}
    stories = [t for t in tickets if t.get("type") == "Story"]
    assert stories
    for story in stories:
        assert story["jira_key"] in trace
    assert approval_status(str(run), "tickets") == (True, "approved")
    assert (run / "prd.md").read_bytes() == prd_before
    assert ux_hash(run) == ux_before


def test_state_is_done_and_valid_after_success(tmp_path):
    run = approved_run(tmp_path)
    fake = FakeJira()
    jira_publish.publish(str(run), str(write_config(tmp_path)), client=make_client(fake))
    state = json.loads((run / "state.json").read_text())
    schema = json.loads((REPO_ROOT / "schemas" / "state.schema.json").read_text())
    assert state["stage"] == "done"
    assert list(Draft202012Validator(schema).iter_errors(state)) == []


def test_success_output_lines(tmp_path, capsys):
    run = approved_run(tmp_path)
    fake = FakeJira()
    jira_publish.publish(str(run), str(write_config(tmp_path)), client=make_client(fake))
    lines = capsys.readouterr().out.strip().splitlines()
    total = len(all_tickets(manifest_of(run)))
    assert len(lines) == total + 1
    assert lines[-1] == f"PUBLISHED: {total} created, 0 updated"
    assert lines[0].startswith("EPIC-01: created DEMO-")


# --- preconditions ---

@pytest.mark.parametrize("site,project_key", [("[[SITE]]", "DEMO"), (SITE, "[[KEY]]")])
def test_placeholders_refuse_before_any_request(tmp_path, site, project_key):
    run = approved_run(tmp_path)
    fake = FakeJira()
    config = write_config(tmp_path, site=site, project_key=project_key)
    with pytest.raises(ValueError, match="placeholder"):
        jira_publish.publish(str(run), str(config), client=make_client(fake))
    assert len(fake.requests) == 0


def test_missing_env_refuses_and_touches_no_network(tmp_path, monkeypatch):
    run = approved_run(tmp_path)
    monkeypatch.delenv("JIRA_EMAIL", raising=False)
    monkeypatch.delenv("JIRA_API_TOKEN", raising=False)

    def boom(*args, **kwargs):
        raise AssertionError("network touched")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    with pytest.raises(ValueError, match="JIRA_EMAIL"):
        jira_publish.publish(str(run), str(write_config(tmp_path)))
    monkeypatch.setenv("JIRA_EMAIL", EMAIL)
    with pytest.raises(ValueError, match="JIRA_API_TOKEN"):
        jira_publish.publish(str(run), str(write_config(tmp_path)))
    assert not (run / "tickets.published.json").exists()


def test_publish_flag_with_dry_run_mode_exits_one(tmp_path, monkeypatch, capsys):
    run = approved_run(tmp_path)
    config = write_config(tmp_path, mode="dry_run")
    monkeypatch.setattr(sys, "argv", ["jira_publish.py", str(run), "--config", str(config), "--publish"])
    with pytest.raises(SystemExit) as exc:
        jira_publish.main()
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "two keys" in err and "--publish" in err
    assert not (run / "tickets.dryrun.json").exists()


def test_publish_mode_without_flag_exits_one(tmp_path, monkeypatch, capsys):
    run = approved_run(tmp_path)
    config = write_config(tmp_path, mode="publish")
    monkeypatch.setattr(sys, "argv", ["jira_publish.py", str(run), "--config", str(config)])
    with pytest.raises(SystemExit) as exc:
        jira_publish.main()
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "two keys" in err and "--publish" in err
    assert not (run / "tickets.dryrun.json").exists()
    assert not (run / "tickets.published.json").exists()


# --- jira_key safety ---

def set_key(run, ticket_id, key):
    manifest = manifest_of(run)
    for ticket in all_tickets(manifest):
        if ticket["id"] == ticket_id:
            ticket["jira_key"] = key
    (run / "tickets.manifest.json").write_text(json.dumps(manifest))


def puts_of(fake):
    return [r for r in fake.requests if r.method == "PUT"]


def test_hand_edited_key_of_unrelated_issue_is_not_overwritten(tmp_path):
    run = approved_run(tmp_path)
    fake = FakeJira()
    original = {"summary": "someone else's issue", "labels": ["unrelated"]}
    other = fake.seed_issue(dict(original))
    set_key(run, "EPIC-01", other)
    assert approval_status(str(run), "tickets") == (True, "approved")
    with pytest.raises(jira_publish.PublishFailed) as exc:
        jira_publish.publish(str(run), str(write_config(tmp_path)), client=make_client(fake))
    slug = manifest_of(run)["prd_slug"]
    assert f"jira_key {other} for EPIC-01 does not carry label ext-{slug}-epic-01" in str(exc.value)
    assert len(puts_of(fake)) == 0
    assert fake.issues[other] == original


def test_hand_edited_key_in_another_project_is_refused(tmp_path):
    run = approved_run(tmp_path)
    fake = FakeJira()
    set_key(run, "EPIC-01", "OTHER-5")
    with pytest.raises(jira_publish.PublishFailed) as exc:
        jira_publish.publish(str(run), str(write_config(tmp_path)), client=make_client(fake))
    assert "jira_key OTHER-5 for EPIC-01 is not in project DEMO" in str(exc.value)
    assert len(puts_of(fake)) == 0
    assert len(fake.requests) == 0


def test_rerun_with_keys_from_previous_publish_still_updates_all(tmp_path):
    run = approved_run(tmp_path)
    fake = FakeJira()
    config = write_config(tmp_path)
    jira_publish.publish(str(run), str(config), client=make_client(fake))
    total = len(all_tickets(manifest_of(run)))
    counts = jira_publish.publish(str(run), str(config), client=make_client(fake))
    assert counts == {"created": 0, "updated": total}
    assert len(puts_of(fake)) == total


# --- blocks in the live description ---

def adf_text(adf):
    out = []

    def walk(node):
        if node.get("type") == "text":
            out.append(node["text"])
        for child in node.get("content", []):
            walk(child)

    walk(adf)
    return "\n".join(out)


def test_blocks_are_listed_in_live_description_only(tmp_path):
    run = make_tickets_run(tmp_path)
    write_state(run)
    manifest = manifest_of(run)
    tickets = {t["id"]: t for t in all_tickets(manifest)}
    tickets["T-001"]["blocks"] = ["T-002"]
    (run / "tickets.manifest.json").write_text(json.dumps(manifest))
    result = subprocess.run(
        [sys.executable, "scripts/approve.py", str(run), "tickets",
         "--decisions-file", str(run / "decisions.test.md")],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stderr
    summary = tickets["T-002"]["summary"]

    entries = jira_publish.build_dryrun(manifest, "DEMO", ["agentic-pm"])
    dry = next(e for e in entries if e["ticket_id"] == "T-001")
    assert "Blocks" not in dry["payload"]["fields"]["description"]

    fake = FakeJira()
    config = write_config(tmp_path)
    jira_publish.publish(str(run), str(config), client=make_client(fake))
    first = next(p for p in issue_posts(fake) if p.body["fields"]["summary"] == tickets["T-001"]["summary"])
    text = adf_text(first.body["fields"]["description"])
    assert "Blocks:" in text and f"T-002: {summary}" in text  # T-002 has no key yet

    jira_publish.publish(str(run), str(config), client=make_client(fake))
    key = manifest_of(run)["epics"][0]["children"][1]["jira_key"]
    put = next(r for r in puts_of(fake) if r.body["fields"]["summary"] == tickets["T-001"]["summary"])
    assert f"T-002 ({key}): {summary}" in adf_text(put.body["fields"]["description"])
    other = next(p for p in issue_posts(fake) if p.body["fields"]["summary"] == summary)
    assert "Blocks" not in adf_text(other.body["fields"]["description"])


# --- lost create response ---

def test_lost_create_response_is_adopted_not_duplicated(tmp_path):
    run = approved_run(tmp_path)
    fake = FakeJira()
    fake.lose_response_on_create()
    counts = jira_publish.publish(str(run), str(write_config(tmp_path)), client=make_client(fake))
    manifest = manifest_of(run)
    total = len(all_tickets(manifest))
    assert counts == {"created": total, "updated": 0}
    assert len(fake.issues) == total
    label = f"ext-{manifest['prd_slug']}-epic-01"
    assert [k for k, f in fake.issues.items() if label in f["labels"]] == [manifest["epics"][0]["jira_key"]]
    assert json.loads((run / "tickets.published.json").read_text())[0]["action"] == "created"


def test_plain_500_on_create_is_retried_once(tmp_path):
    run = approved_run(tmp_path)
    fake = FakeJira()
    fake.fail_on_request(2, 500)  # search is request 1, the first create is request 2
    counts = jira_publish.publish(str(run), str(write_config(tmp_path)), client=make_client(fake))
    total = len(all_tickets(manifest_of(run)))
    assert counts == {"created": total, "updated": 0}
    assert len(fake.issues) == total
    assert len(issue_posts(fake)) == total + 1


def test_two_500s_on_create_stop_the_publish(tmp_path):
    run = approved_run(tmp_path)
    fake = FakeJira()
    fake.fail_on_request(2, 500)
    fake.fail_on_request(4, 500)  # search (3) then the retried create (4)
    with pytest.raises(jira_publish.PublishFailed) as exc:
        jira_publish.publish(str(run), str(write_config(tmp_path)), client=make_client(fake))
    assert "FAILED at EPIC-01" in str(exc.value) and "0 published before the failure" in str(exc.value)
    assert len(fake.issues) == 0


# --- small items ---

def test_non_https_site_refused_even_with_injected_client(tmp_path):
    run = approved_run(tmp_path)
    fake = FakeJira()
    config = write_config(tmp_path, site="http://example.atlassian.net")
    with pytest.raises(ValueError, match="https://"):
        jira_publish.publish(str(run), str(config), client=make_client(fake))
    assert len(fake.requests) == 0


def test_unexpected_transport_exception_is_one_line_failure(tmp_path, monkeypatch, env, capsys):
    run = approved_run(tmp_path)
    config = write_config(tmp_path)

    def broken(method, url, headers, body, timeout):
        raise RuntimeError("boom\nsecond line")

    monkeypatch.setattr(jira_client, "default_transport", broken)
    monkeypatch.setattr(sys, "argv", ["jira_publish.py", str(run), "--config", str(config), "--publish"])
    with pytest.raises(SystemExit) as exc:
        jira_publish.main()
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert err.startswith("FAILED") and len(err.strip().splitlines()) == 1
    assert "Traceback" not in err and TOKEN not in err
