"""End-to-end M7 on the ai-clear-fit fixture: Gate C approval, then a live publish against the fake Jira."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import jira_publish  # noqa: E402
from check_approval import approval_status  # noqa: E402
from fake_jira import FakeJira  # noqa: E402
from jira_client import JiraClient  # noqa: E402
from ux_hash import ux_hash  # noqa: E402

GOLDEN = REPO / "fixtures" / "ai-clear-fit" / "golden"
SITE = "https://example.atlassian.net"


def run_script(*args):
    return subprocess.run([sys.executable, *map(str, args)], capture_output=True, text=True, cwd=REPO)


def approved_fixture_run(tmp_path: Path) -> Path:
    decisions = tmp_path / "decisions.test.md"
    decisions.write_text("# Decisions\n\n")
    intake = run_script(
        "scripts/intake.py", REPO / "fixtures" / "ai-clear-fit" / "notes.md", "--date", "2026-01-15",
        "--slug", "ai-clear-fit", "--runs-dir", tmp_path,
    )
    assert intake.returncode == 0, intake.stderr
    run = Path(json.loads(intake.stdout)["run_dir"])
    for name in ("01-extraction.json", "02-problem.md", "prd.md", "prd.audit.json"):
        shutil.copy(GOLDEN / name, run / name)
    assert run_script("scripts/render_audit.py", run).returncode == 0
    approve_prd = run_script("scripts/approve.py", run, "prd", "--decisions-file", decisions)
    assert approve_prd.returncode == 0, approve_prd.stdout + approve_prd.stderr

    shutil.copytree(GOLDEN / "ux", run / "ux")
    shutil.copy(GOLDEN / "ux.audit.json", run / "ux.audit.json")
    assert run_script("scripts/render_ux_audit.py", run).returncode == 0
    approve_ux = run_script("scripts/approve.py", run, "ux", "--decisions-file", decisions)
    assert approve_ux.returncode == 0, approve_ux.stdout + approve_ux.stderr

    shutil.copy(GOLDEN / "tickets.manifest.json", run / "tickets.manifest.json")
    validate = run_script("scripts/validate_tickets.py", run)
    assert validate.returncode == 0, validate.stdout + validate.stderr
    approve_tickets = run_script("scripts/approve.py", run, "tickets", "--decisions-file", decisions)
    assert approve_tickets.returncode == 0, approve_tickets.stdout + approve_tickets.stderr
    return run


def test_offline_end_to_end_gate_c_to_live_publish(tmp_path):
    run = approved_fixture_run(tmp_path)
    prd_before = (run / "prd.md").read_bytes()
    ux_before = ux_hash(run)
    config = tmp_path / "config.yaml"
    config.write_text(yaml.safe_dump({"jira": {
        "mode": "publish", "site": SITE, "project_key": "DEMO", "default_labels": ["agentic-pm"],
    }}))
    fake = FakeJira()
    client = JiraClient(SITE, "someone@example.com", "fake-token", transport=fake.transport,
                        sleep=lambda seconds: None, min_interval=0)

    manifest = json.loads((GOLDEN / "tickets.manifest.json").read_text())
    n_epics = len(manifest["epics"])
    n_children = sum(len(e["children"]) for e in manifest["epics"])
    assert (n_epics, n_children) == (2, 14)

    first = jira_publish.publish(str(run), str(config), client=client)
    assert first == {"created": 16, "updated": 0}
    posts = [r for r in fake.requests if r.method == "POST" and r.path == "/rest/api/3/issue"]
    kinds = [p.body["fields"]["issuetype"]["name"] for p in posts]
    assert kinds[:2] == ["Epic", "Epic"] and "Epic" not in kinds[2:]

    second = jira_publish.publish(str(run), str(config), client=client)
    assert second == {"created": 0, "updated": 16}
    assert len(fake.issues) == 16

    published = json.loads((run / "tickets.manifest.json").read_text())
    keys = [e["jira_key"] for e in published["epics"]] + [
        c["jira_key"] for e in published["epics"] for c in e["children"]
    ]
    assert len(keys) == 16 and all(keys) and len(set(keys)) == 16
    trace = (run / "traceability.md").read_text()
    for epic in published["epics"]:
        for child in epic["children"]:
            if child["type"] == "Story":
                assert child["jira_key"] in trace
    assert approval_status(str(run), "tickets") == (True, "approved")
    assert (run / "prd.md").read_bytes() == prd_before
    assert ux_hash(run) == ux_before
    state = json.loads((run / "state.json").read_text())
    assert state["stage"] == "done" and len(state["jira_keys"]) == 16
