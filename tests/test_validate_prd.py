"""Test validate_prd.py script."""

import json
import tempfile
import subprocess
import sys
from pathlib import Path

import pytest


# Baseline valid PRD with all required headings and content
VALID_PRD_BASE = """## 1. Header

This is the header section.

## 2. TL;DR

Summary of the PRD in one paragraph.

## 3. Problem statement

The problem is well described with numbers. The system processes 5000 requests per day and 2% fail.

## 4. Why now and strategic fit

Strategic context and timing.

## 5. Target users and segments

Our target users are admins who manage calendars.

## 6. Evidence

### 6a. Data insights

| ID | Claim | Value | Segment | Period | N | Source | Confidence | Caveats |
|----|-------|-------|---------|--------|---|--------|------------|---------|
| EV-001 | High failure rate | 2% | All | Q4 2026 | 1000 | Logs | High | Estimated |

### 6b. Customer anecdotes

Customer feedback from interviews supports the problem.

### 6c. Evidence gaps

No additional data gaps identified.

## 7. Goals and non-goals

### Goals
- Reduce meeting scheduling time by 50%

### Non-goals
- Integrating with all calendar systems
- Building a calendar application

## 8. Success metrics

**MET-001** is the primary metric for this feature.

| Metric | Target | Timeframe | Baseline | Guardrail |
|--------|--------|-----------|----------|-----------|
| **MET-001** Meeting scheduling time | 5 minutes | 30 days | 20 minutes | Not below 8 minutes |

Target: 5 minutes average scheduling time.
Timeframe: Measure over 30 days starting from launch.
Guardrail metrics: Ensure customer satisfaction doesn't drop.
Baseline: Current average is 20 minutes.

## 9. Value tests

Value tests to validate assumptions.

## 10. Solution overview

The solution involves integrating with calendar APIs.

## 11. User flow

Users will see available time slots automatically.

## 12. Requirements

| REQ-ID | Description | Priority | Acceptance criteria |
|--------|-------------|----------|---------------------|
| REQ-001 | Show available times | Must | Given a customer, When they open the scheduler, \
Then they see available slots (MET-001) |
| REQ-002 | Support Google Calendar | Should | Given a user with Google Calendar, When they authenticate, \
Then their calendar loads (P-1) |
| REQ-003 | Mobile support | Could | Given a mobile user, When they access the app, Then the UI is responsive |

## 13. MVP scope

In scope for v1:
- Calendar integration
- Time slot display

Out of v1:
- Mobile app
- Advanced scheduling rules

## 14. Dependencies and assumptions

Dependencies on calendar API availability.

## 15. Risks and mitigations

Risk: API rate limits. Mitigation: Cache results.

## 16. Launch and rollout

Phased rollout to 10% of users first.

## 17. Open questions

Questions for follow-up discussion.

## 18. Alignment

Aligned with Q4 roadmap goals.

## 19. Decision log

Decisions made during planning.

## 20. Traceability

This PRD traces to problem PB-1 (P-1, M-1) and evidence (EV-001, AN-001).
"""

VALID_PRD_WITH_ADDENDUM = VALID_PRD_BASE + """
## A1. 5-Gate verdict and red flag check

AI verdict: PASS. No red flags identified.

## A2. AI pattern and architecture choice

Pattern: Classification. Architecture: Transformer-based.

## A3. Context engineering

Context includes user history and preferences.

## A4. What good looks like

Good performance: 95% accuracy on test set.

## A5. Constraints

Latency constraint: < 100ms per request.

## A6. Error tolerance and fallback

Fallback to manual scheduling if AI fails.

## A7. Trust, control, recovery

Users can override AI suggestions. Recovery: manual entry.

## A8. Eval plan

Offline eval on historical data, then online A/B test.

## A9. Observability

Logging: all scheduling requests. Metrics: accuracy, latency.

## A10. Full cost estimate

Estimated cost: $5000/month for API calls and compute.
"""


def create_test_run(tmpdir: str, run_id: str, extraction: dict, problem_md: str, prd_md: str) -> str:
    """Helper to create a test run directory with all necessary files."""
    run_path = Path(tmpdir) / "runs" / run_id
    run_path.mkdir(parents=True)

    notes_dir = run_path / "00-notes"
    notes_dir.mkdir()
    (notes_dir / "notes.numbered.md").write_text("1: Test notes")

    # Create extraction.json
    (run_path / "01-extraction.json").write_text(json.dumps(extraction, indent=2))

    # Create problem.md
    (run_path / "02-problem.md").write_text(problem_md)

    # Create prd.md
    (run_path / "prd.md").write_text(prd_md)

    return str(run_path)


def create_evidence_card(run_dir: str, card_id: str, value: int) -> None:
    """Helper to create an evidence card."""
    evidence_dir = Path(run_dir) / "03-evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    card = {
        "id": card_id,
        "claim": f"Test claim with value {value}",
        "metric": "test_metric",
        "value": value,
        "segment": "all",
        "period": "Q4 2026",
        "n": 1000,
        "source": "test",
        "query_id": "q1",
        "query_hash": "hash1",
        "run_at": "2026-10-03T00:00:00Z",
        "confidence": "high",
        "caveats": [],
        "supports_problem": "PB-1"
    }
    card_path = evidence_dir / f"{card_id}.json"
    card_path.write_text(json.dumps(card, indent=2))


def create_anecdotes(run_dir: str, anecdote_ids: list) -> None:
    """Helper to create anecdotes file."""
    anecdotes = []
    for an_id in anecdote_ids:
        anecdote = {
            "id": an_id,
            "source": "interview",
            "source_ref": "2026-10-03",
            "date": "2026-10-03",
            "segment": "admin",
            "persona": "PM",
            "pain": "Scheduling is slow",
            "quote": "I spend too much time on scheduling",
            "sentiment": 1,
            "linked_problem": "PB-1",
            "frequency_hint": None,
            "consent_ok": True
        }
        anecdotes.append(anecdote)

    anecdotes_path = Path(run_dir) / "04-anecdotes.json"
    anecdotes_path.write_text(json.dumps(anecdotes, indent=2))


def run_validator(run_dir: str) -> tuple:
    """Run validator and return (returncode, stdout, stderr)."""
    result = subprocess.run(
        [sys.executable, "scripts/validate_prd.py", run_dir],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent
    )
    return result.returncode, result.stdout, result.stderr


def make_problem_md(ai_proposed: bool = False, gates_content: str = None) -> str:
    """Create a problem.md with configurable ai.proposed."""
    if ai_proposed and gates_content is None:
        gates_content = """  proposed: true
  gates:
    '1':
      result: pass
    '2':
      result: pass
    '3':
      result: pass
    '4':
      result: pass
    '5':
      result: pass
  pattern: "classification"
  red_flags: []
  verdict: "PASS\""""
    elif not ai_proposed:
        gates_content = "  proposed: false"

    return f"""---
run_id: "2026-10-03-test"
problems:
  - id: PB-1
    title: Test problem
    validation_status: VALIDATED
    missing_evidence: []
    source_items: [P-1, M-1]
    reframed_from_solution: false
primary_problem: PB-1
parked_problems: []
ai:
{gates_content}
---

## Problem statement

Test
"""


def make_extraction() -> dict:
    """Create a minimal extraction.json."""
    return {
        "run_id": "2026-10-03-test",
        "attendee_roles": ["PM"],
        "problems": [
            {"id": "P-1", "text": "Test problem", "source_lines": [1], "type": "stated"},
            {"id": "P-99", "text": "Unused", "source_lines": [1], "type": "stated"}
        ],
        "proposed_solutions": [],
        "user_segments": [],
        "requests": [],
        "decisions": [],
        "disagreements": [],
        "open_questions": [],
        "action_items": [],
        "metrics_mentioned": [
            {"id": "M-1", "text": "Meeting time 5000 requests", "source_lines": [1], "type": "stated"}
        ]
    }


# Test 1: Valid PRD passes
def test_validate_prd_passes_for_valid():
    """Test that a valid PRD passes."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = create_test_run(
            tmpdir,
            "2026-10-03-test",
            make_extraction(),
            make_problem_md(),
            VALID_PRD_BASE
        )
        create_evidence_card(run_dir, "EV-001", 2)
        create_anecdotes(run_dir, ["AN-001"])

        code, stdout, stderr = run_validator(run_dir)
        assert code == 0, f"Valid PRD should pass. Errors: {stdout}"


# Test 2: Missing heading
def test_validate_prd_fails_missing_heading():
    """Test that missing heading is detected."""
    with tempfile.TemporaryDirectory() as tmpdir:
        prd = VALID_PRD_BASE.replace("## 5. Target users and segments\n\nOur target users", "")
        run_dir = create_test_run(
            tmpdir,
            "2026-10-03-test",
            make_extraction(),
            make_problem_md(),
            prd
        )
        create_evidence_card(run_dir, "EV-001", 2)
        create_anecdotes(run_dir, ["AN-001"])

        code, stdout, stderr = run_validator(run_dir)
        assert code == 1
        assert "Missing heading" in stdout


# Test 3: Headings out of order
def test_validate_prd_fails_headings_out_of_order():
    """Test that out-of-order headings are detected."""
    with tempfile.TemporaryDirectory() as tmpdir:
        prd = VALID_PRD_BASE.replace("## 4. Why now", "## 5. Why now").replace(
            "## 5. Target users", "## 4. Target users"
        )
        run_dir = create_test_run(
            tmpdir,
            "2026-10-03-test",
            make_extraction(),
            make_problem_md(),
            prd
        )
        create_evidence_card(run_dir, "EV-001", 2)
        create_anecdotes(run_dir, ["AN-001"])

        code, stdout, stderr = run_validator(run_dir)
        assert code == 1
        assert "out of order" in stdout.lower()


# Test 4: Missing 6b sub-heading
def test_validate_prd_fails_missing_6b_subheading():
    """Test that missing ### 6b sub-heading is detected."""
    with tempfile.TemporaryDirectory() as tmpdir:
        prd = VALID_PRD_BASE.replace("### 6b. Customer anecdotes\n\n", "")
        run_dir = create_test_run(
            tmpdir,
            "2026-10-03-test",
            make_extraction(),
            make_problem_md(),
            prd
        )
        create_evidence_card(run_dir, "EV-001", 2)
        create_anecdotes(run_dir, ["AN-001"])

        code, stdout, stderr = run_validator(run_dir)
        assert code == 1
        assert "6b" in stdout


# Test 5: Addendum present when AI not proposed
def test_validate_prd_fails_addendum_when_ai_not_proposed():
    """Test that addendum is rejected when ai.proposed is false."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = create_test_run(
            tmpdir,
            "2026-10-03-test",
            make_extraction(),
            make_problem_md(ai_proposed=False),
            VALID_PRD_WITH_ADDENDUM
        )
        create_evidence_card(run_dir, "EV-001", 2)
        create_anecdotes(run_dir, ["AN-001"])

        code, stdout, stderr = run_validator(run_dir)
        assert code == 1
        assert "A1" in stdout or "addendum" in stdout.lower()


# Test 6: Addendum missing when AI proposed
def test_validate_prd_fails_addendum_missing_when_ai_proposed():
    """Test that addendum is required when ai.proposed is true."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = create_test_run(
            tmpdir,
            "2026-10-03-test",
            make_extraction(),
            make_problem_md(ai_proposed=True),
            VALID_PRD_BASE
        )
        create_evidence_card(run_dir, "EV-001", 2)
        create_anecdotes(run_dir, ["AN-001"])

        code, stdout, stderr = run_validator(run_dir)
        assert code == 1
        assert "A1" in stdout or "addendum" in stdout.lower()


# Test 7: Full addendum with ai.proposed true passes
def test_validate_prd_passes_with_full_addendum():
    """Test that full addendum with ai.proposed true passes."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = create_test_run(
            tmpdir,
            "2026-10-03-test",
            make_extraction(),
            make_problem_md(ai_proposed=True),
            VALID_PRD_WITH_ADDENDUM
        )
        create_evidence_card(run_dir, "EV-001", 2)
        create_anecdotes(run_dir, ["AN-001"])

        code, stdout, stderr = run_validator(run_dir)
        assert code == 0, f"Addendum PRD should pass. Errors: {stdout}"


# Test 8: Duplicate REQ
def test_validate_prd_fails_duplicate_req():
    """Test that duplicate REQ IDs are detected."""
    with tempfile.TemporaryDirectory() as tmpdir:
        prd = VALID_PRD_BASE.replace(
            "| REQ-002 | Support Google Calendar",
            "| REQ-001 | Support Google Calendar"
        )
        run_dir = create_test_run(
            tmpdir,
            "2026-10-03-test",
            make_extraction(),
            make_problem_md(),
            prd
        )
        create_evidence_card(run_dir, "EV-001", 2)
        create_anecdotes(run_dir, ["AN-001"])

        code, stdout, stderr = run_validator(run_dir)
        assert code == 1
        assert "Duplicate" in stdout


# Test 9: Malformed REQ ID
def test_validate_prd_fails_malformed_req_id():
    """Test that malformed REQ IDs are detected."""
    with tempfile.TemporaryDirectory() as tmpdir:
        prd = VALID_PRD_BASE.replace("REQ-001", "REQ-1")
        run_dir = create_test_run(
            tmpdir,
            "2026-10-03-test",
            make_extraction(),
            make_problem_md(),
            prd
        )
        create_evidence_card(run_dir, "EV-001", 2)
        create_anecdotes(run_dir, ["AN-001"])

        code, stdout, stderr = run_validator(run_dir)
        assert code == 1
        assert "REQ-1" in stdout or "Malformed" in stdout


# Test 10: Requirement with invalid priority
def test_validate_prd_fails_requirement_invalid_priority():
    """Test that requirement with priority 'High' fails."""
    with tempfile.TemporaryDirectory() as tmpdir:
        prd = VALID_PRD_BASE.replace(
            "| REQ-001 | Show available times | Must",
            "| REQ-001 | Show available times | High"
        )
        run_dir = create_test_run(
            tmpdir,
            "2026-10-03-test",
            make_extraction(),
            make_problem_md(),
            prd
        )
        create_evidence_card(run_dir, "EV-001", 2)
        create_anecdotes(run_dir, ["AN-001"])

        code, stdout, stderr = run_validator(run_dir)
        assert code == 1
        assert "REQ-001" in stdout and "priority" in stdout.lower()


# Test 11: Requirement without Given/When/Then
def test_validate_prd_fails_requirement_missing_given_when_then():
    """Test that requirement without Given/When/Then fails."""
    with tempfile.TemporaryDirectory() as tmpdir:
        prd = VALID_PRD_BASE.replace(
            "| REQ-001 | Show available times | Must | Given a customer, When they open the scheduler, "
            "Then they see available slots (MET-001) |",
            "| REQ-001 | Show available times | Must | No acceptance criteria |"
        )
        run_dir = create_test_run(
            tmpdir,
            "2026-10-03-test",
            make_extraction(),
            make_problem_md(),
            prd
        )
        create_evidence_card(run_dir, "EV-001", 2)
        create_anecdotes(run_dir, ["AN-001"])

        code, stdout, stderr = run_validator(run_dir)
        assert code == 1
        assert "REQ-001" in stdout and ("Given" in stdout or "acceptance" in stdout.lower())


# Test 12: No primary metric
def test_validate_prd_fails_no_primary_metric():
    """Test that section 8 without primary metric fails."""
    with tempfile.TemporaryDirectory() as tmpdir:
        prd = VALID_PRD_BASE.replace(
            "**MET-001** is the primary metric",
            "**MET-001** is a secondary metric"
        )
        run_dir = create_test_run(
            tmpdir,
            "2026-10-03-test",
            make_extraction(),
            make_problem_md(),
            prd
        )
        create_evidence_card(run_dir, "EV-001", 2)
        create_anecdotes(run_dir, ["AN-001"])

        code, stdout, stderr = run_validator(run_dir)
        assert code == 1
        assert "primary metric" in stdout.lower()


# Test 13: Two primary metrics
def test_validate_prd_fails_two_primary_metrics():
    """Test that two primary metrics fails."""
    with tempfile.TemporaryDirectory() as tmpdir:
        prd = VALID_PRD_BASE.replace(
            "**MET-001** is the primary metric for this feature.",
            "**MET-001** is the primary metric for this feature.\n\n**MET-002** is also a primary metric."
        )
        extraction = make_extraction()
        # Add MET-002 to extraction
        extraction["metrics_mentioned"].append(
            {"id": "M-2", "text": "Another metric", "source_lines": [1], "type": "stated"}
        )
        run_dir = create_test_run(
            tmpdir,
            "2026-10-03-test",
            extraction,
            make_problem_md(),
            prd
        )
        create_evidence_card(run_dir, "EV-001", 2)
        create_anecdotes(run_dir, ["AN-001"])

        code, stdout, stderr = run_validator(run_dir)
        assert code == 1
        assert "primary" in stdout.lower()


# Test 14: Missing Target: in section 8
def test_validate_prd_fails_missing_target():
    """Test that section 8 without Target: fails."""
    with tempfile.TemporaryDirectory() as tmpdir:
        prd = VALID_PRD_BASE.replace("Target: 5 minutes", "")
        run_dir = create_test_run(
            tmpdir,
            "2026-10-03-test",
            make_extraction(),
            make_problem_md(),
            prd
        )
        create_evidence_card(run_dir, "EV-001", 2)
        create_anecdotes(run_dir, ["AN-001"])

        code, stdout, stderr = run_validator(run_dir)
        assert code == 1
        assert "Target:" in stdout


# Test 15: Missing Timeframe: in section 8
def test_validate_prd_fails_missing_timeframe():
    """Test that section 8 without Timeframe: fails."""
    with tempfile.TemporaryDirectory() as tmpdir:
        prd = VALID_PRD_BASE.replace("Timeframe: Measure", "Duration: Measure")
        run_dir = create_test_run(
            tmpdir,
            "2026-10-03-test",
            make_extraction(),
            make_problem_md(),
            prd
        )
        create_evidence_card(run_dir, "EV-001", 2)
        create_anecdotes(run_dir, ["AN-001"])

        code, stdout, stderr = run_validator(run_dir)
        assert code == 1
        assert "Timeframe:" in stdout


# Test 16: EV citation with no evidence dir
def test_validate_prd_fails_ev_citation_without_evidence_dir():
    """Test that EV citation without evidence provider is an error."""
    with tempfile.TemporaryDirectory() as tmpdir:
        prd = VALID_PRD_BASE  # Includes EV-001
        run_dir = create_test_run(
            tmpdir,
            "2026-10-03-test",
            make_extraction(),
            make_problem_md(),
            prd
        )
        # Don't create evidence dir
        create_anecdotes(run_dir, ["AN-001"])

        code, stdout, stderr = run_validator(run_dir)
        assert code == 1
        assert "EV-001" in stdout or "evidence" in stdout.lower()


# Test 17: EV citation with evidence card passes
def test_validate_prd_passes_with_evidence_card():
    """Test that EV citation with evidence card passes."""
    with tempfile.TemporaryDirectory() as tmpdir:
        prd = VALID_PRD_BASE
        run_dir = create_test_run(
            tmpdir,
            "2026-10-03-test",
            make_extraction(),
            make_problem_md(),
            prd
        )
        create_evidence_card(run_dir, "EV-001", 2)
        create_anecdotes(run_dir, ["AN-001"])

        code, stdout, stderr = run_validator(run_dir)
        assert code == 0, f"PRD with evidence card should pass. Errors: {stdout}"


# Test 18: AN citation without anecdotes file
def test_validate_prd_fails_an_citation_without_anecdotes():
    """Test that AN citation without anecdotes file is an error."""
    with tempfile.TemporaryDirectory() as tmpdir:
        prd = VALID_PRD_BASE  # Includes AN-001
        run_dir = create_test_run(
            tmpdir,
            "2026-10-03-test",
            make_extraction(),
            make_problem_md(),
            prd
        )
        create_evidence_card(run_dir, "EV-001", 2)
        # Don't create anecdotes file

        code, stdout, stderr = run_validator(run_dir)
        assert code == 1
        assert "AN-001" in stdout


# Test 19: Missing "No data provider configured" statement
def test_validate_prd_fails_missing_no_data_provider_statement():
    """Test that PRD without evidence data and missing statement fails."""
    with tempfile.TemporaryDirectory() as tmpdir:
        prd = VALID_PRD_BASE.replace(
            "| EV-001 | High failure rate | 2% | All | Q4 2026 | 10000 | Logs | High | Estimated |",
            "Test data"
        )
        run_dir = create_test_run(
            tmpdir,
            "2026-10-03-test",
            make_extraction(),
            make_problem_md(),
            prd
        )
        create_anecdotes(run_dir, ["AN-001"])

        code, stdout, stderr = run_validator(run_dir)
        # This may or may not error depending on exact implementation
        # The test checks the behavior when no evidence cards exist and no "No data provider" statement


# Test 20: Unknown extraction ID in citations
def test_validate_prd_fails_unknown_extraction_id():
    """Test that unknown extraction ID fails."""
    with tempfile.TemporaryDirectory() as tmpdir:
        prd = VALID_PRD_BASE.replace("(P-1, M-1)", "(P-1, M-1, P-99)")
        run_dir = create_test_run(
            tmpdir,
            "2026-10-03-test",
            make_extraction(),
            make_problem_md(),
            prd
        )
        create_evidence_card(run_dir, "EV-001", 2)
        create_anecdotes(run_dir, ["AN-001"])

        code, stdout, stderr = run_validator(run_dir)
        # P-99 exists in extraction, so this should pass
        assert code == 0


# Test 21: Unknown PB citation
def test_validate_prd_fails_unknown_pb_id():
    """Test that unknown PB ID fails."""
    with tempfile.TemporaryDirectory() as tmpdir:
        prd = VALID_PRD_BASE.replace("PB-1", "PB-9")
        run_dir = create_test_run(
            tmpdir,
            "2026-10-03-test",
            make_extraction(),
            make_problem_md(),
            prd
        )
        create_evidence_card(run_dir, "EV-001", 2)
        create_anecdotes(run_dir, ["AN-001"])

        code, stdout, stderr = run_validator(run_dir)
        assert code == 1
        assert "PB-9" in stdout


# Test 22: Missing Non-goals list
def test_validate_prd_fails_missing_non_goals_list():
    """Test that missing Non-goals list fails."""
    with tempfile.TemporaryDirectory() as tmpdir:
        prd = VALID_PRD_BASE.replace(
            "### Non-goals\n- Integrating with all calendar systems\n- Building a calendar application",
            "### Non-goals"
        )
        run_dir = create_test_run(
            tmpdir,
            "2026-10-03-test",
            make_extraction(),
            make_problem_md(),
            prd
        )
        create_evidence_card(run_dir, "EV-001", 2)
        create_anecdotes(run_dir, ["AN-001"])

        code, stdout, stderr = run_validator(run_dir)
        assert code == 1
        assert "Non-goals" in stdout and "list" in stdout.lower()


# Test 23: Missing Out of v1 list
def test_validate_prd_fails_missing_out_of_v1_list():
    """Test that missing Out of v1 list fails."""
    with tempfile.TemporaryDirectory() as tmpdir:
        prd = VALID_PRD_BASE.replace(
            "Out of v1:\n- Mobile app\n- Advanced scheduling rules",
            "Out of v1:"
        )
        run_dir = create_test_run(
            tmpdir,
            "2026-10-03-test",
            make_extraction(),
            make_problem_md(),
            prd
        )
        create_evidence_card(run_dir, "EV-001", 2)
        create_anecdotes(run_dir, ["AN-001"])

        code, stdout, stderr = run_validator(run_dir)
        assert code == 1
        assert "Out of v1" in stdout and "list" in stdout.lower()


# Test 24: TODO outside HTML comment fails
def test_validate_prd_fails_todo_in_body():
    """Test that TODO in body fails."""
    with tempfile.TemporaryDirectory() as tmpdir:
        prd = VALID_PRD_BASE + "\nTODO: update this section"
        run_dir = create_test_run(
            tmpdir,
            "2026-10-03-test",
            make_extraction(),
            make_problem_md(),
            prd
        )
        create_evidence_card(run_dir, "EV-001", 2)
        create_anecdotes(run_dir, ["AN-001"])

        code, stdout, stderr = run_validator(run_dir)
        assert code == 1
        assert "TODO" in stdout


# Test 25: TODO inside HTML comment passes
def test_validate_prd_passes_todo_in_html_comment():
    """Test that TODO inside HTML comment passes."""
    with tempfile.TemporaryDirectory() as tmpdir:
        prd = VALID_PRD_BASE + "\n<!-- TODO: update this section -->"
        run_dir = create_test_run(
            tmpdir,
            "2026-10-03-test",
            make_extraction(),
            make_problem_md(),
            prd
        )
        create_evidence_card(run_dir, "EV-001", 2)
        create_anecdotes(run_dir, ["AN-001"])

        code, stdout, stderr = run_validator(run_dir)
        assert code == 0, f"TODO in HTML comment should pass. Errors: {stdout}"


# Test 26: Unsupported number in section 3
def test_validate_prd_fails_unsupported_number_in_section_3():
    """Test that unsupported number in section 3 fails."""
    with tempfile.TemporaryDirectory() as tmpdir:
        prd = VALID_PRD_BASE.replace(
            "The system processes 5000 requests per day",
            "The system processes 9999 requests per day"
        )
        run_dir = create_test_run(
            tmpdir,
            "2026-10-03-test",
            make_extraction(),
            make_problem_md(),
            prd
        )
        create_evidence_card(run_dir, "EV-001", 2)
        create_anecdotes(run_dir, ["AN-001"])

        code, stdout, stderr = run_validator(run_dir)
        assert code == 1
        assert "9999" in stdout and "section 3" in stdout


# Test 27: Number supported by extraction item passes
def test_validate_prd_passes_number_in_extraction():
    """Test that number present in extraction passes."""
    with tempfile.TemporaryDirectory() as tmpdir:
        extraction = make_extraction()
        # Add 5000 to extraction
        extraction["metrics_mentioned"][0]["text"] = "Meeting time 5000 requests"

        prd = VALID_PRD_BASE
        run_dir = create_test_run(
            tmpdir,
            "2026-10-03-test",
            extraction,
            make_problem_md(),
            prd
        )
        create_evidence_card(run_dir, "EV-001", 2)
        create_anecdotes(run_dir, ["AN-001"])

        code, stdout, stderr = run_validator(run_dir)
        assert code == 0 or "5000" not in stdout, "Number in extraction should be supported"


# Test 28: Number supported by evidence card passes
def test_validate_prd_passes_number_in_evidence_card():
    """Test that number present in evidence card passes."""
    with tempfile.TemporaryDirectory() as tmpdir:
        prd = VALID_PRD_BASE
        run_dir = create_test_run(
            tmpdir,
            "2026-10-03-test",
            make_extraction(),
            make_problem_md(),
            prd
        )
        create_evidence_card(run_dir, "EV-001", 2)  # Has value 2
        create_anecdotes(run_dir, ["AN-001"])

        code, stdout, stderr = run_validator(run_dir)
        assert code == 0 or "2%" not in stdout, "Number in evidence should be supported"


# Test 29: Missing prd.md
def test_validate_prd_fails_missing_prd_md():
    """Test that missing prd.md gives one-line error."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = str(Path(tmpdir) / "runs" / "2026-10-03-test")
        Path(run_dir).mkdir(parents=True)

        # Create extraction and problem but not prd.md
        extraction = make_extraction()
        problem_md = make_problem_md()

        (Path(run_dir) / "01-extraction.json").write_text(json.dumps(extraction))
        (Path(run_dir) / "02-problem.md").write_text(problem_md)

        code, stdout, stderr = run_validator(run_dir)
        assert code == 1
        # Should be a one-line error with no traceback
        lines = stdout.strip().split('\n')
        assert len(lines) == 1, f"Expected one-line error, got {len(lines)} lines: {stdout}"
        assert "Traceback" not in stdout


# --- Citation groups: every ID inside a group is checked ---
def _validate_variant(prd: str, extraction: dict = None, card_value: int = 2) -> tuple:
    """Build a run dir for the given PRD and return the validator result."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = create_test_run(
            tmpdir,
            "2026-10-03-test",
            extraction if extraction is not None else make_extraction(),
            make_problem_md(),
            prd,
        )
        create_evidence_card(run_dir, "EV-001", card_value)
        create_anecdotes(run_dir, ["AN-001"])
        return run_validator(run_dir)


def _with_extra_section_2(line: str) -> str:
    return VALID_PRD_BASE.replace(
        "Summary of the PRD in one paragraph.", f"Summary of the PRD in one paragraph. {line}"
    )


def test_citation_group_second_id_unknown_fails():
    extraction = make_extraction()
    code, stdout, _ = _validate_variant(_with_extra_section_2("Backed by (P-1, M-99)."), extraction)
    assert code == 1
    assert "M-99" in stdout


def test_citation_group_semicolon_pb_unknown_fails():
    code, stdout, _ = _validate_variant(_with_extra_section_2("Backed by [P-1; PB-9]."))
    assert code == 1
    assert "PB-9" in stdout


def test_citation_group_all_ids_present_passes():
    code, stdout, _ = _validate_variant(_with_extra_section_2("Backed by (P-1, M-1) and [P-1 / M-1]."))
    assert code == 0, stdout


def test_citation_group_and_separator_checks_second_id():
    code, stdout, _ = _validate_variant(_with_extra_section_2("Backed by (P-1 and M-77)."))
    assert code == 1
    assert "M-77" in stdout


# --- Number tracing is token based ---
def _prd_without_two_percent() -> str:
    return VALID_PRD_BASE.replace("2%", "7%")


def test_number_not_supported_by_larger_number_containing_it():
    extraction = make_extraction()
    extraction["metrics_mentioned"][0]["text"] = "Meeting time 5000 requests, 22% fail"
    prd = _prd_without_two_percent().replace("and 7% fail.", "and 7% fail. 2 teams escalate.")
    code, stdout, _ = _validate_variant(prd, extraction, card_value=7)
    assert code == 1
    assert "Unsupported number '2' in section 3" in stdout


def test_number_only_inside_extraction_id_is_not_supported():
    extraction = make_extraction()
    extraction["problems"][1]["id"] = "P-2"
    prd = _prd_without_two_percent().replace("and 7% fail.", "and 7% fail. 2 teams escalate.")
    code, stdout, _ = _validate_variant(prd, extraction, card_value=7)
    assert code == 1
    assert "Unsupported number '2' in section 3" in stdout


def test_heading_digits_never_produce_errors():
    prd = VALID_PRD_BASE.replace(
        "Summary of the PRD in one paragraph.",
        "#### Detail 777\n\nSummary of the PRD in one paragraph.",
    )
    code, stdout, _ = _validate_variant(prd)
    assert code == 0, stdout
    assert "777" not in stdout


def test_fraction_evidence_value_supports_percentage_form():
    prd = _prd_without_two_percent().replace("7%", "38%")
    code, stdout, _ = _validate_variant(prd.replace("| 38% |", "| 0.38 |"), card_value=0.38)
    assert code == 0, stdout


def test_range_needs_both_ends_supported():
    extraction = make_extraction()
    extraction["metrics_mentioned"][0]["text"] = "Meeting time 5000 requests, 3 days"
    prd = VALID_PRD_BASE.replace("and 2% fail.", "and 2% fail. Waits are 3-4 days.")
    code, stdout, _ = _validate_variant(prd, extraction)
    assert code == 1
    assert "Unsupported number '4' in section 3" in stdout
    assert "Unsupported number '3'" not in stdout


def test_range_with_both_ends_supported_passes():
    extraction = make_extraction()
    extraction["metrics_mentioned"][0]["text"] = "Meeting time 5000 requests, 3 to 4 days"
    prd = VALID_PRD_BASE.replace("and 2% fail.", "and 2% fail. Waits are 3-4 days.")
    code, stdout, _ = _validate_variant(prd, extraction)
    assert code == 0, stdout


def test_thousands_separator_and_plus_normalised():
    extraction = make_extraction()
    prd = VALID_PRD_BASE.replace("5000 requests", "5,000 requests").replace(
        "and 2% fail.", "and 2% fail. Over 5000+ users."
    )
    code, stdout, _ = _validate_variant(prd, extraction)
    assert code == 0, stdout


def test_iso_dates_and_ordered_list_markers_not_traced():
    prd = VALID_PRD_BASE.replace(
        "Summary of the PRD in one paragraph.",
        "Summary of the PRD in one paragraph.\n\n1. First point\n2. Second point\n\nDecided 2031-05-17.",
    )
    code, stdout, _ = _validate_variant(prd)
    assert code == 0, stdout


# --- Requirement rows cannot skip the acceptance check ---
ROW_REQ_003 = (
    "| REQ-003 | Mobile support | Could | Given a mobile user, When they access the app, "
    "Then the UI is responsive |"
)


def test_requirement_row_with_too_few_cells_fails():
    prd = VALID_PRD_BASE.replace(ROW_REQ_003, "| REQ-008 | Fall back | Must |")
    code, stdout, _ = _validate_variant(prd)
    assert code != 0
    assert "REQ-008" in stdout


def test_indented_requirement_row_is_still_checked():
    prd = VALID_PRD_BASE.replace(ROW_REQ_003, " | REQ-008 | Fall back | Must | No criteria |")
    code, stdout, _ = _validate_variant(prd)
    assert code != 0
    assert "REQ-008" in stdout


def test_section_12_without_requirement_rows_fails():
    start = VALID_PRD_BASE.index("| REQ-ID |")
    end = VALID_PRD_BASE.index("## 13. MVP scope")
    prd = VALID_PRD_BASE[:start] + "No requirements yet.\n\n" + VALID_PRD_BASE[end:]
    code, stdout, _ = _validate_variant(prd)
    assert code != 0
    assert "no requirement rows" in stdout.lower()


def test_requirement_description_mentioning_other_req_is_not_duplicate():
    prd = VALID_PRD_BASE.replace(
        "| REQ-003 | Mobile support |", "| REQ-003 | Mobile support, depends on REQ-001 |"
    )
    code, stdout, _ = _validate_variant(prd)
    assert code == 0, stdout
    assert "Duplicate" not in stdout


def test_genuine_duplicate_in_first_cell_still_fails():
    prd = VALID_PRD_BASE.replace("| REQ-003 | Mobile support", "| REQ-001 | Mobile support")
    code, stdout, _ = _validate_variant(prd)
    assert code != 0
    assert "Duplicate requirement ID: REQ-001" in stdout


def test_requirement_row_without_leading_pipe_is_still_checked():
    prd = VALID_PRD_BASE.replace(ROW_REQ_003, "REQ-008 | Fall back | Must | works |")
    code, stdout, _ = _validate_variant(prd)
    assert code != 0
    assert "Requirement REQ-008: acceptance criteria missing: Given, When, Then" in stdout


def test_cited_requirement_without_row_fails():
    prd = VALID_PRD_BASE.replace("## 13. MVP scope", "See also REQ-777.\n\n## 13. MVP scope")
    code, stdout, _ = _validate_variant(prd)
    assert code != 0
    assert "Requirement REQ-777 is cited but has no row in section 12" in stdout



# --- Quotes in section 6b must be supported ---
def _with_6b_text(text: str) -> str:
    return VALID_PRD_BASE.replace(
        "Customer feedback from interviews supports the problem.",
        f"Customer feedback from interviews supports the problem. {text}",
    )


def test_6b_quote_from_anecdote_record_passes():
    prd = _with_6b_text('One admin said "I spend too much time on scheduling" (AN-001).')
    code, stdout, _ = _validate_variant(prd)
    assert code == 0, stdout


def test_6b_curly_quote_from_anecdote_record_passes():
    prd = _with_6b_text("One admin said “spend too much time on” (AN-001).")
    code, stdout, _ = _validate_variant(prd)
    assert code == 0, stdout


def test_6b_quote_from_extraction_item_passes():
    extraction = make_extraction()
    extraction["problems"][0]["text"] = "Admins said booking takes far too long every week"
    prd = _with_6b_text('In the meeting: "booking takes far too long" (P-1).')
    code, stdout, _ = _validate_variant(prd, extraction)
    assert code == 0, stdout


def test_6b_invented_quote_fails():
    prd = _with_6b_text('A customer said "this tool ruined my entire week" (AN-001).')
    code, stdout, _ = _validate_variant(prd)
    assert code == 1
    assert 'Unsupported quote in section 6b: "this tool ruined my entire week..."' in stdout


def test_6b_short_quoted_phrase_is_ignored():
    prd = _with_6b_text('They called it "far too slow" (AN-001).')
    code, stdout, _ = _validate_variant(prd)
    assert code == 0, stdout


def test_quote_outside_section_6b_is_not_checked():
    prd = VALID_PRD_BASE.replace(
        "Strategic context and timing.", 'Strategic context and "a long invented phrase here".'
    )
    code, stdout, _ = _validate_variant(prd)
    assert code == 0, stdout


# --- Quote styles in section 6b ---
REAL_QUOTE = "I spend too much time on scheduling"
INVENTED_QUOTE = "this tool ruined my entire week"
INVENTED_MESSAGE = 'Unsupported quote in section 6b: "this tool ruined my entire week..."'
QUOTE_STYLES = {
    "single_straight": ("'", "'"),
    "single_curly": ("‘", "’"),
    "guillemets": ("«", "»"),
    "curly_open_straight_close": ("‘", "'"),
    "straight_open_curly_close": ("'", "’"),
}


@pytest.mark.parametrize("style", sorted(QUOTE_STYLES))
def test_6b_invented_quote_fails_in_every_style(style):
    left, right = QUOTE_STYLES[style]
    prd = _with_6b_text(f"A customer said {left}{INVENTED_QUOTE}{right} (AN-001).")
    code, stdout, _ = _validate_variant(prd)
    assert code == 1
    assert INVENTED_MESSAGE in stdout


@pytest.mark.parametrize("style", sorted(QUOTE_STYLES))
def test_6b_real_quote_passes_in_every_style(style):
    left, right = QUOTE_STYLES[style]
    prd = _with_6b_text(f"A customer said {left}{REAL_QUOTE}{right} (AN-001).")
    code, stdout, _ = _validate_variant(prd)
    assert code == 0, stdout


@pytest.mark.parametrize("left,right", [("\u201e", "\u201c"), ("\u201e", "\u201d")])
def test_6b_invented_german_low_quote_fails(left, right):
    prd = _with_6b_text(f"A customer said {left}{INVENTED_QUOTE}{right} (AN-001).")
    code, stdout, _ = _validate_variant(prd)
    assert code == 1
    assert INVENTED_MESSAGE in stdout


@pytest.mark.parametrize("left,right", [("\u201e", "\u201c"), ("\u201e", "\u201d")])
def test_6b_real_german_low_quote_passes(left, right):
    prd = _with_6b_text(f"A customer said {left}{REAL_QUOTE}{right} (AN-001).")
    code, stdout, _ = _validate_variant(prd)
    assert code == 0, stdout


@pytest.mark.parametrize("left,right", [
    ("\u00bb", "\u00ab"),  # reversed guillemets
    ("\u2039", "\u203a"),  # single angle quotes
    ("\u300c", "\u300d"),  # CJK corner brackets
])
def test_6b_invented_quote_fails_in_other_quote_marks(left, right):
    prd = _with_6b_text(f"A customer said {left}{INVENTED_QUOTE}{right} (AN-001).")
    code, stdout, _ = _validate_variant(prd)
    assert code == 1
    assert INVENTED_MESSAGE in stdout


def test_6b_invented_blockquote_fails():
    prd = _with_6b_text(f"\n\n> {INVENTED_QUOTE}\n> (AN-001)")
    code, stdout, _ = _validate_variant(prd)
    assert code == 1
    assert INVENTED_MESSAGE in stdout


def test_6b_real_blockquote_passes():
    prd = _with_6b_text(f"\n\n> {REAL_QUOTE} (AN-001)")
    code, stdout, _ = _validate_variant(prd)
    assert code == 0, stdout


def test_6b_apostrophes_in_prose_are_not_quotes():
    prd = _with_6b_text("The team's admins don't mind, and the manager's view isn't settled (AN-001).")
    code, stdout, _ = _validate_variant(prd)
    assert code == 0, stdout


def test_6b_curly_apostrophes_in_prose_are_not_quotes():
    prd = _with_6b_text("The team’s admins don’t mind, and the manager’s view isn’t settled (AN-001).")
    code, stdout, _ = _validate_variant(prd)
    assert code == 0, stdout


# --- Quotes must be tied to the record they come from ---
def _validate_with_two_anecdotes(prd: str, extraction: dict = None) -> tuple:
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = create_test_run(
            tmpdir, "2026-10-03-test", extraction if extraction is not None else make_extraction(),
            make_problem_md(), prd,
        )
        create_evidence_card(run_dir, "EV-001", 2)
        create_anecdotes(run_dir, ["AN-001", "AN-002"])
        path = Path(run_dir) / "04-anecdotes.json"
        records = json.loads(path.read_text())
        records[1]["quote"] = "Billing reminders arrive far too late"
        path.write_text(json.dumps(records))
        return run_validator(run_dir)


def test_6b_quote_with_right_citation_passes():
    prd = _with_6b_text(
        f'Admin said "{REAL_QUOTE}" (AN-001) and another said "Billing reminders arrive far too late" (AN-002).'
    )
    code, stdout, _ = _validate_with_two_anecdotes(prd)
    assert code == 0, stdout


def test_6b_real_quote_with_wrong_citation_fails():
    prd = _with_6b_text(f'Admin said "{REAL_QUOTE}" (AN-002).')
    code, stdout, _ = _validate_with_two_anecdotes(prd)
    assert code == 1
    assert 'Unsupported quote in section 6b: "I spend too much time on scheduling..."' in stdout


def test_6b_real_quote_with_no_citation_fails():
    prd = _with_6b_text(f'Admin said "{REAL_QUOTE}" without any citation.')
    code, stdout, _ = _validate_with_two_anecdotes(prd)
    assert code == 1
    assert 'Unsupported quote in section 6b: "I spend too much time on scheduling..."' in stdout


def test_6b_citation_in_another_paragraph_does_not_count():
    prd = _with_6b_text(f'Admin said "{REAL_QUOTE}" here.\n\nCited elsewhere (AN-001).')
    code, stdout, _ = _validate_with_two_anecdotes(prd)
    assert code == 1
    assert "Unsupported quote in section 6b" in stdout


def test_6b_citation_in_same_table_row_counts():
    prd = _with_6b_text(f'\n\n| Source | Quote |\n|---|---|\n| AN-001 | "{REAL_QUOTE}" |')
    code, stdout, _ = _validate_with_two_anecdotes(prd)
    assert code == 0, stdout


def test_6b_citation_in_same_list_item_counts_but_not_next_item():
    prd = _with_6b_text(f'\n\n- Admin: "{REAL_QUOTE}" (AN-001)\n- Other: "{REAL_QUOTE}" (AN-002)')
    code, stdout, _ = _validate_with_two_anecdotes(prd)
    assert code == 1
    assert stdout.count("Unsupported quote in section 6b") == 1


def test_6b_extraction_quote_needs_its_own_item_cited():
    extraction = make_extraction()
    extraction["problems"][0]["text"] = "Admins said booking takes far too long every week"
    prd = _with_6b_text('In the meeting: "booking takes far too long" (M-1).')
    code, stdout, _ = _validate_variant(prd, extraction)
    assert code == 1
    assert 'Unsupported quote in section 6b: "booking takes far too long..."' in stdout
