"""Test scripts/active_run.py and that intake sets the pointer only for the repo's own runs/."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import active_run  # noqa: E402

REPO_ROOT = Path(__file__).parent.parent


@pytest.fixture
def pointer_backup():
    """Save and restore runs/.active so tests never change the developer's pointer."""
    runs = REPO_ROOT / "runs"
    runs.mkdir(exist_ok=True)
    pointer = runs / ".active"
    before = pointer.read_bytes() if pointer.exists() else None
    yield pointer
    if before is None:
        if pointer.exists():
            pointer.unlink()
    else:
        pointer.write_bytes(before)


def test_get_active_missing_file(tmp_path):
    (tmp_path / "runs").mkdir()
    assert active_run.get_active(tmp_path) is None


def test_get_active_no_runs_folder(tmp_path):
    assert active_run.get_active(tmp_path) is None


def test_get_active_empty_file(tmp_path):
    (tmp_path / "runs").mkdir()
    (tmp_path / "runs" / ".active").write_text("\n", encoding="utf-8")
    assert active_run.get_active(tmp_path) is None


def test_get_active_unknown_run_folder(tmp_path):
    (tmp_path / "runs").mkdir()
    (tmp_path / "runs" / ".active").write_text("2026-01-01-gone\n", encoding="utf-8")
    assert active_run.get_active(tmp_path) is None


def test_get_active_returns_run_dir(tmp_path):
    (tmp_path / "runs" / "2026-01-01-demo").mkdir(parents=True)
    (tmp_path / "runs" / ".active").write_text("2026-01-01-demo\n", encoding="utf-8")
    assert active_run.get_active(tmp_path) == tmp_path / "runs" / "2026-01-01-demo"


def test_get_active_rejects_path_traversal(tmp_path):
    (tmp_path / "runs").mkdir()
    (tmp_path / "outside").mkdir()
    (tmp_path / "runs" / ".active").write_text("../outside\n", encoding="utf-8")
    assert active_run.get_active(tmp_path) is None


def test_set_active_refuses_dir_outside_repo_runs(tmp_path):
    other = tmp_path / "runs" / "x"
    other.mkdir(parents=True)
    with pytest.raises(ValueError):
        active_run.set_active(other)


def test_set_active_refuses_nested_dir(pointer_backup):
    nested = REPO_ROOT / "runs" / "some-run" / "inner"
    with pytest.raises(ValueError):
        active_run.set_active(nested)


def test_set_and_get_round_trip(pointer_backup):
    run = REPO_ROOT / "runs" / "2026-10-04-active-run-test"
    run.mkdir(parents=True)
    try:
        active_run.set_active(run)
        assert pointer_backup.read_text(encoding="utf-8").strip() == run.name
        assert active_run.get_active(REPO_ROOT) == run
    finally:
        run.rmdir()


def test_intake_into_temp_runs_dir_leaves_pointer_untouched(pointer_backup):
    before = pointer_backup.read_bytes() if pointer_backup.exists() else None
    with tempfile.TemporaryDirectory() as tmp:
        notes = Path(tmp) / "n.md"
        notes.write_text("Line 1\nLine 2\n", encoding="utf-8")
        result = subprocess.run(
            [sys.executable, "scripts/intake.py", str(notes), "--slug", "temp-run",
             "--date", "2026-10-04", "--runs-dir", str(Path(tmp) / "runs")],
            capture_output=True, text=True, cwd=REPO_ROOT,
        )
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)["run_id"] == "2026-10-04-temp-run"
    after = pointer_backup.read_bytes() if pointer_backup.exists() else None
    assert after == before
