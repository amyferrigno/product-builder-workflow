"""Tests for the no-PRD memo template, validator and golden memo."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from validate_memo import MEMO_HEADINGS, validate_memo

FIXTURE = "solution-first-chatbot"
GOLDEN_MEMO = REPO_ROOT / "fixtures" / FIXTURE / "golden" / "no-prd-memo.md"


@pytest.fixture
def run_dir(tmp_path: Path) -> Path:
    result = subprocess.run(
        [
            sys.executable, "scripts/intake.py",
            str(REPO_ROOT / "fixtures" / FIXTURE / "notes.md"),
            "--slug", FIXTURE,
            "--runs-dir", str(tmp_path),
            "--date", "2026-01-15",
        ],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stderr
    run = Path(json.loads(result.stdout)["run_dir"])
    for golden in (REPO_ROOT / "fixtures" / FIXTURE / "golden").iterdir():
        if golden.is_file():
            shutil.copy(golden, run / golden.name)
    return run


def write_memo(run: Path, text: str) -> None:
    (run / "no-prd-memo.md").write_text(text, encoding="utf-8")


def edited(old: str, new: str) -> str:
    text = GOLDEN_MEMO.read_text(encoding="utf-8")
    assert old in text
    return text.replace(old, new, 1)


def test_template_has_seven_headings_in_order():
    text = (REPO_ROOT / "templates" / "no-prd-memo.md").read_text(encoding="utf-8")
    headings = [line[3:].strip() for line in text.split("\n") if line.startswith("## ")]
    assert headings == MEMO_HEADINGS
    assert len(headings) == 7


def test_golden_memo_validates(run_dir: Path):
    assert validate_memo(str(run_dir)) == []


def test_cli_exit_codes(run_dir: Path):
    ok = subprocess.run([sys.executable, "scripts/validate_memo.py", str(run_dir)],
                        capture_output=True, text=True, cwd=REPO_ROOT)
    assert ok.returncode == 0
    (run_dir / "no-prd-memo.md").unlink()
    bad = subprocess.run([sys.executable, "scripts/validate_memo.py", str(run_dir)],
                         capture_output=True, text=True, cwd=REPO_ROOT)
    assert bad.returncode == 1
    assert "Traceback" not in bad.stdout + bad.stderr


def test_missing_file(run_dir: Path):
    (run_dir / "no-prd-memo.md").unlink()
    assert validate_memo(str(run_dir)) == ["no-prd-memo.md not found"]


def test_missing_heading(run_dir: Path):
    write_memo(run_dir, edited("## 6. Parked solution idea", "## Parked"))
    errors = validate_memo(str(run_dir))
    assert any("Missing heading: ## 6. Parked solution idea" in e for e in errors)


def test_headings_out_of_order(run_dir: Path):
    text = GOLDEN_MEMO.read_text(encoding="utf-8")
    text = text.replace("## 3. Why not now", "## TMP").replace(
        "## 4. What would change this", "## 3. Why not now").replace("## TMP", "## 4. What would change this")
    write_memo(run_dir, text)
    assert "Headings out of order" in validate_memo(str(run_dir))


def test_empty_section(run_dir: Path):
    text = GOLDEN_MEMO.read_text(encoding="utf-8")
    start = text.index("## 5. Cheapest next step")
    end = text.index("## 6. Parked solution idea")
    write_memo(run_dir, text[:start] + "## 5. Cheapest next step\n\n<!-- only a comment -->\n\n" + text[end:])
    errors = validate_memo(str(run_dir))
    assert any("Section is empty: ## 5. Cheapest next step" in e for e in errors)


def test_section_1_needs_no_prd(run_dir: Path):
    write_memo(run_dir, edited("No PRD yet", "Not yet"))
    assert any("Section 1" in e for e in validate_memo(str(run_dir)))


def test_section_2_needs_problem_id(run_dir: Path):
    write_memo(run_dir, edited("PB-1: support", "Support"))
    assert any("Section 2" in e and "PB-1" in e for e in validate_memo(str(run_dir)))


def test_unknown_citation_id(run_dir: Path):
    write_memo(run_dir, edited("(P-2, Q-3)", "(P-2, Q-9)"))
    assert any("Q-9" in e for e in validate_memo(str(run_dir)))


def test_invented_number_in_section_3(run_dir: Path):
    write_memo(run_dir, edited("maybe a few hundred tickets", "maybe 700 tickets"))
    assert "Unsupported number '700' in section 3" in validate_memo(str(run_dir))


def test_section_4_needs_two_items(run_dir: Path):
    text = GOLDEN_MEMO.read_text(encoding="utf-8")
    start = text.index("- Confirmation from the support team")
    end = text.index("## 5. Cheapest next step")
    write_memo(run_dir, text[:start] + "\n" + text[end:])
    assert any("Section 4" in e for e in validate_memo(str(run_dir)))


def test_todo_text(run_dir: Path):
    write_memo(run_dir, edited("It is unvalidated.", "It is unvalidated. TODO check."))
    assert "Found TODO in memo text" in validate_memo(str(run_dir))


def test_memo_wrapped_in_code_block_is_rejected(run_dir: Path):
    text = GOLDEN_MEMO.read_text(encoding="utf-8")
    write_memo(run_dir, "```markdown\n" + text + "\n```\n")
    errors = validate_memo(str(run_dir))
    assert any("Missing heading: ## 1. Decision" in e for e in errors)


def test_tilde_fence_is_ignored_too(run_dir: Path):
    text = GOLDEN_MEMO.read_text(encoding="utf-8")
    write_memo(run_dir, "~~~\n" + text + "\n~~~\n")
    assert any("Missing heading" in e for e in validate_memo(str(run_dir)))


def test_section_with_only_a_code_block_is_empty(run_dir: Path):
    text = GOLDEN_MEMO.read_text(encoding="utf-8")
    start = text.index("## 5. Cheapest next step")
    end = text.index("## 6. Parked solution idea")
    write_memo(run_dir, text[:start] + "## 5. Cheapest next step\n\n```\nsome text\n```\n\n" + text[end:])
    assert any("Section is empty: ## 5. Cheapest next step" in e for e in validate_memo(str(run_dir)))


def test_heading_inside_code_block_is_ignored(run_dir: Path):
    write_memo(run_dir, edited("## 7. Sources", "```\n## 8. Hidden\n```\n\n## 7. Sources"))
    assert validate_memo(str(run_dir)) == []


def test_extra_heading_inside_section_3_is_rejected(run_dir: Path):
    write_memo(run_dir, edited("- Nobody has confirmed", "## Notes\n\n- Nobody has confirmed"))
    assert any("Unexpected heading: ## Notes" in e for e in validate_memo(str(run_dir)))


def test_extra_numbered_heading_is_rejected(run_dir: Path):
    text = GOLDEN_MEMO.read_text(encoding="utf-8")
    write_memo(run_dir, text + "\n## 8. Extra\n\nMore text.\n")
    assert any("Unexpected heading: ## 8. Extra" in e for e in validate_memo(str(run_dir)))


def test_section_4_items_need_three_words(run_dir: Path):
    text = GOLDEN_MEMO.read_text(encoding="utf-8")
    start = text.index("- Ticket counts by question type")
    end = text.index("## 5. Cheapest next step")
    write_memo(run_dir, text[:start] + "- a\n- b\n\n" + text[end:])
    errors = validate_memo(str(run_dir))
    assert any("Section 4: list item needs at least three words: - a" in e for e in errors)
    assert any("- b" in e for e in errors)


def test_extraction_that_is_a_json_list_gives_clean_error(run_dir: Path):
    (run_dir / "01-extraction.json").write_text("[1, 2]", encoding="utf-8")
    errors = validate_memo(str(run_dir))
    assert "01-extraction.json must be a JSON object" in errors
    result = subprocess.run([sys.executable, "scripts/validate_memo.py", str(run_dir)],
                            capture_output=True, text=True, cwd=REPO_ROOT)
    assert result.returncode == 1
    assert "Traceback" not in result.stdout + result.stderr
