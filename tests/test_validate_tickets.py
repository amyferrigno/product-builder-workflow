"""Test scripts/validate_tickets.py (Definition of Ready)."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).parent))
from validate_tickets import validate_tickets
from tickets_helpers import make_tickets_run, valid_manifest, write_manifest


def story(m):
    return m["epics"][0]["children"][0]


def children(m):
    return m["epics"][0]["children"]


def has(errors, *needles):
    return any(all(n in e for n in needles) for e in errors)


@pytest.mark.parametrize("ai", [False, True])
def test_valid_manifest_passes(tmp_path, ai):
    run = make_tickets_run(tmp_path, ai=ai)
    assert validate_tickets(run) == []


def _drop_label(m):
    story(m)["labels"] = [x for x in story(m)["labels"] if not x.startswith("ext-")]


def _spike_cycle(m):
    kids = children(m)
    kids[0]["blocks"] = [kids[1]["id"]]
    kids[1]["blocks"] = [kids[0]["id"]]


def _drop_instrumentation(m):
    m["epics"][0]["children"] = [c for c in children(m) if c.get("task_kind") != "instrumentation"]


def _drop_measure(m):
    m["epics"][1]["kind"] = "feature"


def _uncover_must(m):
    story(m)["req_ids"] = ["REQ-002"]


# (id, edit, needles expected in one error, ai)
CASES = [
    ("rule1-run-id", lambda m: m.update(run_id="other"), ("run_id",), False),
    ("rule1-bad-id", lambda m: story(m).update(id="X-1"), ("X-1", "T-###"), False),
    ("rule1-duplicate-id", lambda m: children(m)[1].update(id="T-001"), ("T-001", "duplicate"), False),
    ("rule1-missing-idempotency-label", _drop_label, ("T-001", "ext-"), False),
    ("rule1-ai-label-missing", lambda m: story(m).update(labels=[x for x in story(m)["labels"] if x != "ai-feature"]),
     ("T-001", "ai-feature"), True),
    ("rule1-ai-label-unexpected", lambda m: story(m)["labels"].append("ai-feature"), ("T-001", "ai-feature"), False),
    ("rule1-schema-story-points", lambda m: story(m).update(story_points=3), ("T-001", "schema"), False),
    ("rule2-too-long", lambda m: story(m).update(summary="[Scheduling] Deliver " + "x" * 80), ("T-001", "too long"), False),
    ("rule2-wrong-format", lambda m: story(m).update(summary="deliver the thing"), ("T-001", "[Area] Verb object"), False),
    ("rule3-todo", lambda m: story(m).update(description="TODO write the real description of this story later"),
     ("T-001", "TODO"), False),
    ("rule3-tbd-criterion", lambda m: story(m)["acceptance_criteria"].__setitem__(0, "Given a, When b, Then TBD"),
     ("T-001", "TBD"), False),
    ("rule3-todos-substring", lambda m: story(m).update(description="TODOs remain in this description of the story"),
     ("T-001", "TODO"), False),
    ("rule3-todo-underscore", lambda m: story(m).update(description="Deliver the thing, TODO_later for the user"),
     ("T-001", "TODO"), False),
    ("rule3-tbd-glued", lambda m: story(m).update(description="Deliver the valueTBD thing for the user please"),
     ("T-001", "TBD"), False),
    ("rule1-foreign-ext-label", lambda m: story(m)["labels"].append(f"ext-{m['prd_slug']}-t-002"),
     ("T-001", "another ticket"), False),
    ("rule1-label-upper-case", lambda m: story(m)["labels"].append("Agentic-PM"),
     ("T-001", "label 'Agentic-PM'", "invalid"), False),
    ("rule1-label-with-space", lambda m: story(m)["labels"].append("two words"),
     ("T-001", "label 'two words'", "invalid"), False),
    ("rule1-label-leading-space-ext", lambda m: story(m)["labels"].append(f" ext-{m['prd_slug']}-t-002"),
     ("T-001", "invalid"), False),
    ("rule8-blank-ai-criterion", lambda m: story(m).update(ai_quality_criteria=["  "]),
     ("T-001", "blank", "ai_quality_criteria"), True),
    ("rule9-task-blank-criterion", lambda m: m["epics"][1]["children"][0].update(acceptance_criteria=[""]),
     ("acceptance_criteria", "blank"), False),
    ("rule4-spaces-description", lambda m: story(m).update(description=" " * 40),
     ("T-001", "description shorter"), False),
    ("rule3-placeholder", lambda m: story(m).update(description="Deliver [[THING]] for the user so they can work"),
     ("T-001", "[["), False),
    ("rule4-short-description", lambda m: story(m).update(description="Too short"), ("T-001", "description"), False),
    ("rule4-priority", lambda m: story(m).update(priority="high"), ("T-001", "priority"), False),
    ("rule5-problem-ref", lambda m: m["epics"][0].update(problem_ref="PB-99"), ("EPIC-01", "PB-99"), False),
    ("rule5-empty-epic", lambda m: m["epics"][1].update(children=[]), ("EPIC-02", "no child"), False),
    ("rule5-no-instrumentation", _drop_instrumentation, ("EPIC-01", "instrumentation"), False),
    ("rule5-no-measure-epic", _drop_measure, ("measure_quality",), False),
    ("rule6-no-req", lambda m: story(m).update(req_ids=[]), ("T-001", "req_ids"), False),
    ("rule6-unknown-req", lambda m: story(m).update(req_ids=["REQ-999"]), ("T-001", "REQ-999"), False),
    ("rule6-two-criteria", lambda m: story(m)["acceptance_criteria"].pop(), ("T-001", "at least 3"), False),
    ("rule6-no-gwt", lambda m: story(m)["acceptance_criteria"].__setitem__(0, "It works well"),
     ("T-001", "Given, When, Then"), False),
    ("rule6-partial-gwt", lambda m: story(m)["acceptance_criteria"].__setitem__(0, "Given a, When b"),
     ("T-001", "Then"), False),
    ("rule6-no-user-facing", lambda m: story(m).pop("user_facing"), ("T-001", "user_facing"), False),
    ("rule7-no-screen", lambda m: story(m).update(screen_ids=[]), ("T-001", "screen"), False),
    ("rule7-unknown-screen", lambda m: story(m).update(screen_ids=["SCR-099"]), ("T-001", "SCR-099"), False),
    ("rule7-no-event", lambda m: story(m).update(analytics_events=[]), ("T-001", "analytics"), False),
    ("rule7-unknown-event", lambda m: story(m).update(analytics_events=["made_up_event"]),
     ("T-001", "made_up_event"), False),
    ("rule8-no-ai-criteria", lambda m: story(m).update(ai_quality_criteria=[]), ("T-001", "ai_quality_criteria"), True),
    ("rule9-task-no-kind", lambda m: children(m)[-1].pop("task_kind") if "task_kind" in children(m)[-1]
     else m["epics"][1]["children"][0].pop("task_kind"), ("task_kind",), False),
    ("rule9-task-no-criteria", lambda m: m["epics"][1]["children"][0].update(acceptance_criteria=[]),
     ("task", "at least 1 acceptance criterion"), False),
    ("rule9-spike-no-ref", lambda m: next(c for c in children(m) if c["type"] == "Spike").update(open_question_ref=""),
     ("spike", "open_question_ref"), False),
    ("rule9-spike-no-criteria", lambda m: next(c for c in children(m) if c["type"] == "Spike")
     .update(acceptance_criteria=[]), ("spike", "at least 1 acceptance criterion"), False),
    ("rule10-uncovered-must", _uncover_must, ("REQ-001", "not covered"), False),
    ("rule11-unknown-block", lambda m: story(m).update(blocks=["T-999"]), ("T-001", "T-999"), False),
    ("rule11-self-block", lambda m: story(m).update(blocks=["T-001"]), ("T-001", "itself"), False),
    ("rule11-cycle", _spike_cycle, ("cycle",), False),
    ("rule12-child-jira-key", lambda m: story(m).update(jira_key="PROJ-1"), ("T-001", "jira_key"), False),
    ("rule12-epic-jira-key", lambda m: m["epics"][0].update(jira_key="PROJ-9"), ("EPIC-01", "jira_key"), False),
]


@pytest.mark.parametrize("name,edit,needles,ai", CASES, ids=[c[0] for c in CASES])
def test_rejections(tmp_path, name, edit, needles, ai):
    run = make_tickets_run(tmp_path, ai=ai)
    manifest = valid_manifest(run, ai)
    edit(manifest)
    write_manifest(run, manifest)
    errors = validate_tickets(run)
    assert has(errors, *needles), errors


def test_rule6_second_story_error_names_that_story(tmp_path):
    run = make_tickets_run(tmp_path)
    manifest = valid_manifest(run, False)
    children(manifest)[1]["acceptance_criteria"].pop()
    write_manifest(run, manifest)
    errors = validate_tickets(run)
    assert has(errors, "T-002", "at least 3")
    assert not has(errors, "T-001")


def test_missing_manifest_and_bad_json(tmp_path):
    run = make_tickets_run(tmp_path)
    (run / "tickets.manifest.json").unlink()
    assert has(validate_tickets(run), "not found")
    (run / "tickets.manifest.json").write_text("{nope")
    assert has(validate_tickets(run), "JSON")


def test_cli_exit_codes_and_no_traceback(tmp_path):
    run = make_tickets_run(tmp_path)
    ok = subprocess.run([sys.executable, "scripts/validate_tickets.py", str(run)],
                        capture_output=True, text=True, cwd=REPO_ROOT)
    assert ok.returncode == 0 and ok.stdout == ""
    manifest = json.loads((run / "tickets.manifest.json").read_text())
    manifest["epics"][0]["children"][0]["acceptance_criteria"].pop()
    write_manifest(run, manifest)
    bad = subprocess.run([sys.executable, "scripts/validate_tickets.py", str(run)],
                         capture_output=True, text=True, cwd=REPO_ROOT)
    assert bad.returncode == 1 and "T-001" in bad.stdout and "Traceback" not in bad.stderr
