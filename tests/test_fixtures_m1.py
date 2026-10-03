"""Test M1 fixtures: all golden outputs pass validators and match expectations."""

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
import yaml


FIXTURES = [
    "clean-meeting",
    "messy-transcript",
    "solution-first-chatbot",
    "contradictory-decisions",
    "thin-evidence",
    "ai-clear-fit",
]


def run_intake(fixture_name: str, tmpdir: str, run_id: str) -> str:
    """Run intake to create a run directory with numbered notes."""
    repo_root = Path(__file__).parent.parent
    fixture_path = repo_root / "fixtures" / fixture_name / "notes.md"

    # Extract date (format: YYYY-MM-DD-slug, date is first 10 chars)
    date_str = run_id[:10]

    result = subprocess.run(
        [
            sys.executable, "scripts/intake.py",
            str(fixture_path),
            "--slug", fixture_name,
            "--runs-dir", tmpdir,
            "--date", date_str
        ],
        capture_output=True,
        text=True,
        cwd=repo_root
    )

    if result.returncode != 0:
        raise RuntimeError(f"Intake failed: {result.stderr}")

    output = json.loads(result.stdout)
    return output["run_dir"]


def copy_golden_files(fixture_name: str, run_dir: str):
    """Copy golden extraction and problem files to run directory."""
    repo_root = Path(__file__).parent.parent
    golden_dir = repo_root / "fixtures" / fixture_name / "golden"

    if golden_dir.exists():
        for golden_file in ["01-extraction.json", "02-problem.md"]:
            golden_path = golden_dir / golden_file
            if golden_path.exists():
                target_path = Path(run_dir) / golden_file
                target_path.write_text(golden_path.read_text())


def run_validator(script_name: str, run_dir: str) -> tuple:
    """Run a validator script. Returns (returncode, stdout, stderr)."""
    repo_root = Path(__file__).parent.parent
    result = subprocess.run(
        [sys.executable, f"scripts/{script_name}", run_dir],
        capture_output=True,
        text=True,
        cwd=repo_root
    )
    return result.returncode, result.stdout, result.stderr


def load_expected(fixture_name: str) -> dict:
    """Load expected.yaml for a fixture."""
    repo_root = Path(__file__).parent.parent
    expected_path = repo_root / "fixtures" / fixture_name / "expected.yaml"
    with open(expected_path) as f:
        return yaml.safe_load(f)


def load_problem_frontmatter(run_dir: str) -> dict:
    """Load YAML front matter from problem.md."""
    problem_path = Path(run_dir) / "02-problem.md"
    with open(problem_path) as f:
        content = f.read()

    if not content.startswith('---'):
        raise ValueError("problem.md must start with ---")

    lines = content.split('\n')
    end_idx = None
    for i in range(1, len(lines)):
        if lines[i] == '---':
            end_idx = i
            break

    if end_idx is None:
        raise ValueError("Missing closing --- in problem.md")

    front_matter_text = '\n'.join(lines[1:end_idx])
    return yaml.safe_load(front_matter_text)


def load_problem_body(run_dir: str) -> str:
    """Load the body of problem.md (after front matter)."""
    problem_path = Path(run_dir) / "02-problem.md"
    with open(problem_path) as f:
        content = f.read()

    lines = content.split('\n')
    end_idx = None
    for i in range(1, len(lines)):
        if lines[i] == '---':
            end_idx = i
            break

    if end_idx is None:
        raise ValueError("Missing closing --- in problem.md")

    return '\n'.join(lines[end_idx + 1:])


def load_extraction(run_dir: str) -> dict:
    """Load extraction.json."""
    extraction_path = Path(run_dir) / "01-extraction.json"
    with open(extraction_path) as f:
        return json.load(f)


def assert_key_known(key: str, allowed_keys: set):
    """Fail loudly if key is unknown."""
    assert key in allowed_keys, f"Unknown key in expected.yaml: {key}. Allowed: {allowed_keys}"


def assert_run_id(expected: dict, fm: dict):
    """Assert run_id matches."""
    assert fm.get("run_id") == expected["run_id"], \
        f"run_id mismatch: {fm.get('run_id')} != {expected['run_id']}"


def assert_problem_count(expected: dict, fm: dict):
    """Assert problem count."""
    assert len(fm.get("problems", [])) == expected["problem_count"], \
        f"problem_count mismatch: {len(fm.get('problems', []))} != {expected['problem_count']}"


def assert_primary_problem_id(expected: dict, fm: dict):
    """Assert primary_problem_id."""
    assert fm.get("primary_problem") == expected["primary_problem_id"], \
        f"primary_problem mismatch: {fm.get('primary_problem')} != {expected['primary_problem_id']}"


def assert_primary_problem_validation_status(expected: dict, fm: dict):
    """Assert primary problem's validation_status."""
    primary_id = expected["primary_problem_id"]
    problems = {p["id"]: p for p in fm.get("problems", [])}
    assert primary_id in problems, f"primary_problem {primary_id} not in problems"
    assert problems[primary_id]["validation_status"] == expected["primary_problem_validation_status"], \
        f"primary_problem validation_status mismatch: {problems[primary_id]['validation_status']} != {expected['primary_problem_validation_status']}"


def assert_parked_problem_count(expected: dict, fm: dict):
    """Assert parked_problem count."""
    assert len(fm.get("parked_problems", [])) == expected["parked_problem_count"], \
        f"parked_problem_count mismatch: {len(fm.get('parked_problems', []))} != {expected['parked_problem_count']}"


def assert_ai_proposed(expected: dict, fm: dict):
    """Assert ai.proposed."""
    assert fm.get("ai", {}).get("proposed") == expected["ai_proposed"], \
        f"ai.proposed mismatch: {fm.get('ai', {}).get('proposed')} != {expected['ai_proposed']}"


def assert_ai_verdict(expected: dict, fm: dict):
    """Assert ai.verdict (for specific verdict)."""
    if "ai_verdict" in expected:
        actual_verdict = fm.get("ai", {}).get("verdict")
        expected_verdict = expected["ai_verdict"]
        assert actual_verdict == expected_verdict, \
            f"ai.verdict mismatch: {actual_verdict} != {expected_verdict}"


def assert_ai_verdict_allowed(expected: dict, fm: dict):
    """Assert ai.verdict is in allowed list."""
    if "ai_verdict_allowed" in expected:
        actual_verdict = fm.get("ai", {}).get("verdict")
        allowed = expected["ai_verdict_allowed"]
        assert actual_verdict in allowed, \
            f"ai.verdict {actual_verdict} not in allowed: {allowed}"


def assert_must_have_open_questions(expected: dict, problem_body: str):
    """Assert open questions section exists if required."""
    if expected.get("must_have_open_questions"):
        assert "## Open questions" in problem_body, \
            "must_have_open_questions=true but 'Open questions' section missing"


def assert_must_have_disagreements(expected: dict, extraction: dict):
    """Assert disagreements exist if required."""
    if expected.get("must_have_disagreements"):
        disagreements = extraction.get("disagreements", [])
        assert len(disagreements) > 0, \
            "must_have_disagreements=true but no disagreements in extraction"


def assert_must_have_reframed_from_solution(expected: dict, fm: dict):
    """Assert reframed_from_solution=true if required."""
    if expected.get("must_have_reframed_from_solution"):
        problems = fm.get("problems", [])
        assert len(problems) > 0, "No problems found"
        primary_id = fm.get("primary_problem")
        primary = next((p for p in problems if p["id"] == primary_id), None)
        assert primary is not None, f"Primary problem {primary_id} not found"
        assert primary.get("reframed_from_solution") is True, \
            "must_have_reframed_from_solution=true but primary problem has reframed_from_solution != true"


def assert_contradictory_decisions_open_questions(expected: dict, problem_body: str, extraction: dict):
    """For contradictory-decisions: assert Owner: line and cites both sides."""
    if expected.get("must_have_disagreements"):
        # Find the Open questions section
        assert "## Open questions" in problem_body, "Open questions section missing"

        # Extract the open questions section
        lines = problem_body.split('\n')
        open_q_idx = None
        for i, line in enumerate(lines):
            if line.startswith("## Open questions"):
                open_q_idx = i
                break

        assert open_q_idx is not None, "Open questions section not found"

        # Find the next section or end of file
        next_section_idx = len(lines)
        for i in range(open_q_idx + 1, len(lines)):
            if lines[i].startswith("## "):
                next_section_idx = i
                break

        open_q_section = '\n'.join(lines[open_q_idx:next_section_idx])

        # Assert Owner: line exists
        assert "Owner:" in open_q_section, "Open questions section missing 'Owner:' line"

        # Get disagreement items from extraction
        disagreements = extraction.get("disagreements", [])
        assert len(disagreements) > 0, "No disagreements found in extraction"

        # Collect all line numbers from disagreements
        all_source_lines = set()
        for disagreement in disagreements:
            all_source_lines.update(disagreement.get("source_lines", []))

        assert len(all_source_lines) > 0, "No source_lines in disagreements"

        # Assert at least two distinct line numbers are cited in open questions section
        cited_lines = set()
        # Extract line numbers from text like "line 5" or "lines 10, 16"
        for group in re.findall(r'lines?[\s:]*(\d+(?:\s*,\s*\d+)*)', open_q_section, re.IGNORECASE):
            for match in re.findall(r'\d+', group):
                line_num = int(match)
                if line_num in all_source_lines:
                    cited_lines.add(line_num)

        assert len(cited_lines) >= 2, \
            f"Open questions should cite at least 2 distinct line numbers from disagreements, found {cited_lines}"


@pytest.mark.parametrize("fixture_name", FIXTURES)
def test_fixture_golden_outputs(fixture_name: str):
    """Test that fixture golden outputs pass validators and match expected.yaml."""
    expected = load_expected(fixture_name)

    with tempfile.TemporaryDirectory() as tmpdir:
        run_id = expected["run_id"]
        run_dir = run_intake(fixture_name, tmpdir, run_id)
        copy_golden_files(fixture_name, run_dir)

        # Validate extraction
        code, stdout, stderr = run_validator("validate_extraction.py", run_dir)
        assert code == 0, f"Extraction validation failed for {fixture_name}: {stdout}{stderr}"

        # Validate problem
        code, stdout, stderr = run_validator("validate_problem.py", run_dir)
        assert code == 0, f"Problem validation failed for {fixture_name}: {stdout}{stderr}"

        # Load front matter and extraction
        fm = load_problem_frontmatter(run_dir)
        problem_body = load_problem_body(run_dir)
        extraction = load_extraction(run_dir)

        # Define allowed keys
        allowed_keys = {
            "run_id", "problem_count", "primary_problem_id", "primary_problem_validation_status",
            "parked_problem_count", "ai_proposed", "ai_verdict", "ai_verdict_allowed",
            "must_have_open_questions", "must_have_disagreements", "must_have_reframed_from_solution"
        }

        # Assert each key in expected.yaml
        for key in expected:
            assert_key_known(key, allowed_keys)

        # Run assertion helpers
        assert_run_id(expected, fm)
        assert_problem_count(expected, fm)
        assert_primary_problem_id(expected, fm)
        assert_primary_problem_validation_status(expected, fm)
        assert_parked_problem_count(expected, fm)
        assert_ai_proposed(expected, fm)
        assert_ai_verdict(expected, fm)
        assert_ai_verdict_allowed(expected, fm)
        assert_must_have_open_questions(expected, problem_body)
        assert_must_have_disagreements(expected, extraction)
        assert_must_have_reframed_from_solution(expected, fm)

        # Special case for contradictory-decisions
        if fixture_name == "contradictory-decisions":
            assert_contradictory_decisions_open_questions(expected, problem_body, extraction)
