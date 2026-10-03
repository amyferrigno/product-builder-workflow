"""Golden UX for the ai-clear-fit fixture (M5)."""
import json
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from ux_hash import ux_hash  # noqa: E402
from validate_prd import parse_requirements  # noqa: E402
from validate_ux import validate_ux  # noqa: E402

GOLDEN = REPO / "fixtures" / "ai-clear-fit" / "golden"
STATES = [
    "default", "loading", "empty", "error", "success",
    "low-confidence", "user-edit", "regenerate", "explanation", "escalation",
]
DIMENSIONS = {
    "req_coverage", "required_states", "ai_trust_control_recovery",
    "accessibility", "token_consistency", "copy_clarity",
}


def make_run(tmp_path: Path) -> Path:
    run = tmp_path / "run"
    run.mkdir()
    shutil.copy(GOLDEN / "prd.md", run / "prd.md")
    shutil.copytree(GOLDEN / "ux", run / "ux")
    return run


def test_golden_ux_validates(tmp_path):
    assert validate_ux(make_run(tmp_path), repo_root=REPO) == []


def test_audit_hash_matches_golden_ux(tmp_path):
    audit = json.loads((GOLDEN / "ux.audit.json").read_text())
    assert audit["ux_hash"] == ux_hash(make_run(tmp_path))


def test_every_screen_has_all_ten_states():
    screens = sorted((GOLDEN / "ux" / "screens").glob("SCR-*.html"))
    assert 2 <= len(screens) <= 4
    for screen in screens:
        text = screen.read_text()
        for state in STATES:
            assert f'id="state-{state}" data-state="{state}"' in text, (screen.name, state)


def test_every_must_requirement_is_in_the_spec():
    prd = (GOLDEN / "prd.md").read_text()
    spec = (GOLDEN / "ux" / "spec.md").read_text()
    musts = [req for req, priority in parse_requirements(prd) if priority == "Must"]
    assert musts
    for req in musts:
        assert req in spec, req


def test_golden_audit_shape():
    audit = json.loads((GOLDEN / "ux.audit.json").read_text())
    ids = [d["id"] for d in audit["dimensions"]]
    assert sorted(ids) == sorted(DIMENSIONS)
    assert audit["ai_feature"] is True
    for dim in audit["dimensions"]:
        if dim["score"] < 3:
            assert dim.get("fix") and dim.get("screens")
