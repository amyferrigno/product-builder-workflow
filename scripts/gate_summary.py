#!/usr/bin/env python3
"""
Print a one-screen summary of a PRD artifact.
Usage: python scripts/gate_summary.py <run_dir> prd|ux
"""

import sys
import json
import re
from pathlib import Path

import yaml

SCRIPTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPTS_DIR.parent
sys.path.insert(0, str(SCRIPTS_DIR))


def load_json_file(file_path: Path) -> dict:
    """Load a JSON file."""
    try:
        with open(file_path, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, IOError):
        return None


def load_markdown_file(file_path: Path) -> str:
    """Load a markdown file."""
    try:
        with open(file_path, 'r') as f:
            return f.read()
    except (FileNotFoundError, IOError):
        return None


def extract_section_content(markdown: str, section_number: int, section_title: str) -> str:
    """Extract content of a specific section from markdown."""
    if not markdown:
        return None

    # Pattern: ## <number>. <title> ... (until the next "## " heading or end).
    # Sub-headings (###) belong to the section.
    pattern = rf"^## {section_number}\. {re.escape(section_title)}$(.+?)(?=^## |\Z)"
    match = re.search(pattern, markdown, re.MULTILINE | re.DOTALL)

    if match:
        return match.group(1).strip()
    return None


def extract_primary_metric(markdown: str) -> str:
    """Extract primary metric from section 8."""
    content = extract_section_content(markdown, 8, "Success metrics")
    if not content:
        return None

    # Look for lines containing "Primary metric"
    lines = content.split('\n')
    for line in lines:
        if "Primary metric" in line:
            cleaned = re.sub(r'^\s*(?:[-*+]|\d+\.)\s+', '', line)
            cleaned = cleaned.replace('**', '').strip()
            # The summary line already carries the "Primary metric:" label
            return re.sub(r'\s*Primary metric:\s*', ' ', cleaned, flags=re.IGNORECASE).strip()

    return None


def extract_list_items(text: str, max_items: int = 5) -> tuple:
    """Extract list items from text. Returns (items, total_count)."""
    if not text:
        return [], 0

    # Find bullet points (lines starting with - or *)
    lines = text.split('\n')
    all_items = [
        line.strip()[2:].strip()
        for line in lines
        if line.strip().startswith(('- ', '* '))
    ]

    # No bullets: fall back to table rows (header and separator rows skipped)
    if not all_items:
        all_items = extract_table_rows(lines)

    return all_items[:max_items], len(all_items)


def extract_table_rows(lines: list) -> list:
    """Return markdown table body rows as 'cell (cell, ...)' strings."""
    rows = []
    header_seen = False
    for line in lines:
        stripped = line.strip()
        if not (stripped.startswith('|') and stripped.endswith('|')):
            continue
        cells = [cell.strip() for cell in stripped.strip('|').split('|')]
        if all(re.fullmatch(r':?-+:?', cell) for cell in cells):
            continue
        if not header_seen:
            header_seen = True
            continue
        cells = [cell for cell in cells if cell]
        if cells:
            extra = f" ({', '.join(cells[1:])})" if len(cells) > 1 else ""
            rows.append(cells[0] + extra)
    return rows


def extract_problem_from_file(run_dir: str) -> tuple:
    """Return (id, title, validation_status) of the primary problem from 02-problem.md."""
    content = load_markdown_file(Path(run_dir) / "02-problem.md")
    if not content or not content.startswith('---'):
        return None, None, None

    lines = content.split('\n')
    end_idx = None
    for i in range(1, len(lines)):
        if lines[i] == '---':
            end_idx = i
            break
    if end_idx is None:
        return None, None, None

    try:
        front_matter = yaml.safe_load('\n'.join(lines[1:end_idx]))
    except yaml.YAMLError:
        return None, None, None
    if not isinstance(front_matter, dict):
        return None, None, None

    primary = front_matter.get("primary_problem")
    for prob in front_matter.get("problems") or []:
        if isinstance(prob, dict) and prob.get("id") == primary:
            return prob.get("id"), prob.get("title"), prob.get("validation_status")
    return None, None, None


def get_prd_audit_scores(run_dir: str) -> dict:
    """Load per-dimension scores from prd.audit.json."""
    audit = load_json_file(Path(run_dir) / "prd.audit.json")
    scores = {}
    if not isinstance(audit, dict):
        return scores
    for dim in audit.get("dimensions", []):
        dim_id = dim.get("id")
        score = dim.get("score")
        if dim_id and score:
            scores[dim_id] = score
    return scores


def blocking_dimensions() -> set:
    """Ids of blocking dimensions from the audit rubric."""
    try:
        from audit_verdict import load_rubric
        rubric = load_rubric(REPO_ROOT)
    except Exception:
        return set()
    return {d.get("id") for d in rubric.get("dimensions", []) if d.get("blocking")}


def resolve_verdict(run_dir: str, state: dict):
    """Verdict from state.json, else computed from prd.audit.json, else None."""
    verdicts = (state or {}).get("verdicts") or {}
    if verdicts.get("prd"):
        return verdicts["prd"]

    run_path = Path(run_dir)
    audit = load_json_file(run_path / "prd.audit.json")
    if not isinstance(audit, dict):
        return None
    try:
        from audit_verdict import compute_verdict, hash_file, load_rubric, prd_has_ai_addendum
        prd_path = run_path / "prd.md"
        has_ai = prd_has_ai_addendum(prd_path.read_text())
        verdict, _ = compute_verdict(audit, load_rubric(REPO_ROOT), hash_file(prd_path), has_ai)
        return verdict
    except Exception:
        return None


def split_scope(section_text: str) -> tuple:
    """Split section 13 into (in_text, out_text) at the 'Out of v1' label."""
    if not section_text:
        return "", ""
    match = re.search(r'^.*out of v1.*$', section_text, re.MULTILINE | re.IGNORECASE)
    if not match:
        return section_text, ""
    return section_text[:match.start()], section_text[match.end():]


def ux_gate_summary(run_dir: str) -> None:
    """Print a short summary of the UX artifact for Human Gate B."""
    from ux_verdict import load_ux_rubric
    from validate_prd import parse_requirements
    from validate_ux import spec_screen_reqs, validate_ux

    run_path = Path(run_dir)
    prd_content = load_markdown_file(run_path / "prd.md")
    if prd_content is None:
        print("Error: prd.md not found", file=sys.stderr)
        sys.exit(1)
    if not (run_path / "ux").is_dir():
        print("Error: ux folder not found", file=sys.stderr)
        sys.exit(1)

    state_path = run_path / "state.json"
    state = (load_json_file(state_path) if state_path.exists() else None) or {}
    run_id = state.get("run_id", "unknown")
    verdict = (state.get("verdicts") or {}).get("ux")

    audit = load_json_file(run_path / "ux.audit.json")
    dims = audit.get("dimensions", []) if isinstance(audit, dict) else []
    try:
        blocking = {d.get("id") for d in load_ux_rubric(REPO_ROOT).get("dimensions", []) if d.get("blocking")}
    except Exception:
        blocking = set()

    screens = sorted((run_path / "ux" / "screens").glob("SCR-*.html"))

    requirements = parse_requirements(prd_content)
    must = [r for r, priority in requirements if priority == "Must"]
    covered = set()
    spec_text = load_markdown_file(run_path / "ux" / "spec.md")
    if spec_text:
        for reqs in spec_screen_reqs(spec_text).values():
            covered.update(reqs)
    must_covered = [r for r in must if r in covered]

    errors = validate_ux(run_dir, REPO_ROOT)

    lines = ["=" * 60, "UX Gate Summary", "=" * 60, f"Run ID: {run_id}"]
    lines.append(f"Audit Verdict: {verdict if verdict else 'not available'}")
    if dims:
        lines.append("Scores by dimension (* = blocking):")
        for dim in dims:
            mark = " *" if dim.get("id") in blocking else ""
            lines.append(f"  {dim.get('id')}: {dim.get('score')}{mark}")
    lines.append(f"Screens: {len(screens)}")
    lines.append(f"Must requirements covered: {len(must_covered)} of {len(must)}")
    if errors:
        lines.append(f"Script check errors ({len(errors)}):")
        lines.extend(f"  - {e}" for e in errors)
    else:
        lines.append("Script check errors: none")

    fixes = []
    for dim in dims:
        score = dim.get("score")
        if isinstance(score, int) and score < 3 and dim.get("fix"):
            screens_txt = f" (screens: {', '.join(dim['screens'])})" if dim.get("screens") else ""
            fixes.append(f"  - {dim.get('id')}: {dim['fix']}{screens_txt}")
    if fixes:
        lines.append("Fixes for scores below 3:")
        lines.extend(fixes)

    if verdict in ("PASS", "PASS_WITH_RISK"):
        lines.append(f"Next step: Approve with /pm-approve ux {run_id} or send change requests")
    elif verdict == "FAIL":
        lines.append(
            f"Next step: verdict is FAIL; fix the screens above, or approve with /pm-approve ux {run_id} and an explicit override reason"
        )
    else:
        lines.append("Next step: run the audit first")
    lines.append("=" * 60)
    for line in lines:
        print(line)


def gate_summary(run_dir: str, artifact: str) -> None:
    """Print a one-screen summary."""

    if artifact == "ux":
        ux_gate_summary(run_dir)
        return

    run_path = Path(run_dir)

    # Load PRD
    prd_path = run_path / "prd.md"
    if not prd_path.exists():
        print("Error: prd.md not found", file=sys.stderr)
        sys.exit(1)

    prd_content = load_markdown_file(prd_path)

    # Load state
    state_path = run_path / "state.json"
    state = load_json_file(state_path) if state_path.exists() else {}

    # Extract run ID
    run_id = state.get("run_id", "unknown")

    # Extract problem info from 02-problem.md
    problem_id, problem_title, validation_status = extract_problem_from_file(str(run_path))
    if problem_title:
        status_str = f" ({validation_status})" if validation_status else ""
        problem_str = f"{problem_id}: {problem_title}{status_str}"
    else:
        problem_str = "not available"

    # Extract primary metric
    primary_metric = extract_primary_metric(prd_content) or "not available"

    # Extract scope in and out
    scope_content = extract_section_content(prd_content, 13, "MVP scope")
    scope_in_text, scope_out_text = split_scope(scope_content)
    scope_in_items, scope_in_total = extract_list_items(scope_in_text, max_items=5)
    scope_out_items, scope_out_total = extract_list_items(scope_out_text, max_items=5)

    # Extract audit info
    verdict = resolve_verdict(str(run_path), state)
    scores = get_prd_audit_scores(str(run_path))
    blocking = blocking_dimensions()

    # Extract open questions
    open_q_content = extract_section_content(prd_content, 17, "Open questions")
    open_q_items, open_q_total = extract_list_items(open_q_content, max_items=5)

    lines = []
    lines.append("=" * 60)
    lines.append("PRD Gate Summary")
    lines.append("=" * 60)
    lines.append(f"Run ID: {run_id}")
    lines.append(f"Problem: {problem_str}")
    lines.append(f"Primary metric: {primary_metric}")

    for label, items, total in (
        ("MVP Scope (in)", scope_in_items, scope_in_total),
        ("MVP Scope (out)", scope_out_items, scope_out_total),
    ):
        lines.append(f"{label}:")
        if items:
            lines.extend(f"  - {item}" for item in items)
            if total > len(items):
                lines.append(f"  (+{total - len(items)} more)")
        else:
            lines.append("  not available")

    lines.append(f"Audit Verdict: {verdict if verdict else 'not available'}")
    if scores:
        lines.append("Scores by dimension (* = blocking):")
        for dim_id, score in scores.items():
            mark = " *" if dim_id in blocking else ""
            lines.append(f"  {dim_id}: {score}{mark}")

    lines.append("Open Questions:")
    if open_q_items:
        lines.extend(f"  - {item}" for item in open_q_items)
        if open_q_total > len(open_q_items):
            lines.append(f"  (+{open_q_total - len(open_q_items)} more)")
    else:
        lines.append("  not available")

    lines.append("Cost: not metered until M8")
    if verdict in ("PASS", "PASS_WITH_RISK"):
        lines.append(f"Next step: Approve with /pm-approve prd {run_id} or send change requests")
    elif verdict == "FAIL":
        lines.append("Next step: verdict is FAIL; revise the flagged sections, or approve with an explicit override reason")
    else:
        lines.append("Next step: run the audit first")
    lines.append("=" * 60)

    for line in lines:
        print(line)


def main():
    """Main entry point."""
    if len(sys.argv) != 3:
        print("Usage: python scripts/gate_summary.py <run_dir> prd|ux", file=sys.stderr)
        sys.exit(1)

    run_dir = sys.argv[1]
    artifact = sys.argv[2]

    try:
        gate_summary(run_dir, artifact)
    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
