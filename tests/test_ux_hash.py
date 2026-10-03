"""Test scripts/ux_hash.py."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).parent))
from ux_hash import ux_hash
from ux_helpers import make_ux_run


def test_stable_across_calls(tmp_path):
    run = make_ux_run(tmp_path)
    assert ux_hash(run) == ux_hash(run)
    assert len(ux_hash(run)) == 64


@pytest.mark.parametrize("rel", [
    "flows.md", "spec.md", "index.html", "screens/SCR-001-home.html", "screens/SCR-002-details.html",
])
def test_changes_when_a_file_changes(tmp_path, rel):
    run = make_ux_run(tmp_path)
    before = ux_hash(run)
    path = run / "ux" / rel
    path.write_bytes(path.read_bytes() + b" ")
    assert ux_hash(run) != before


def test_unaffected_by_unrelated_files(tmp_path):
    run = make_ux_run(tmp_path)
    before = ux_hash(run)
    (run / "state.json").write_text("{}")
    (run / "notes.txt").write_text("x")
    (run / "ux" / "notes.txt").write_text("x")
    (run / "prd.md").write_text("changed")
    assert ux_hash(run) == before


def test_missing_ux_folder_raises(tmp_path):
    with pytest.raises(ValueError):
        ux_hash(tmp_path)
