#!/usr/bin/env python3
"""
Validate no-prd-memo.md against structure and traceability rules.
Usage: python scripts/validate_memo.py <run_dir>

Reuses the citation, number-tracing and comment helpers of validate_prd.py.
"""

import re
import sys
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))

import validate_prd as vp  # noqa: E402

MEMO_HEADINGS = [
    "1. Decision",
    "2. Problem hypothesis",
    "3. Why not now",
    "4. What would change this",
    "5. Cheapest next step",
    "6. Parked solution idea",
    "7. Sources",
]


def split_sections(text: str) -> Dict[str, str]:
    """Map each memo heading found (in the text) to its body, up to the next ## heading."""
    sections: Dict[str, str] = {}
    current = None
    for line in text.split('\n'):
        if line.startswith('## '):
            current = line[3:].strip()
            sections.setdefault(current, "")
        elif current is not None:
            sections[current] += line + "\n"
    return sections


def validate_memo(run_dir: str) -> List[str]:
    """Return a list of error strings for no-prd-memo.md in run_dir (empty means valid)."""
    run_path = Path(run_dir)
    memo_path = run_path / "no-prd-memo.md"
    if not memo_path.is_file():
        return ["no-prd-memo.md not found"]
    try:
        raw = memo_path.read_text(encoding="utf-8")
    except (IOError, UnicodeDecodeError) as e:
        return [f"Cannot read no-prd-memo.md: {e}"]

    errors: List[str] = []
    text = vp.remove_html_comments(raw)

    # Headings present, in order, non-empty
    found_order = [line[3:].strip() for line in text.split('\n') if line.startswith('## ')]
    sections = split_sections(text)
    for heading in MEMO_HEADINGS:
        if heading not in sections:
            errors.append(f"Missing heading: ## {heading}")
        elif not sections[heading].strip():
            errors.append(f"Section is empty: ## {heading}")
    present = [h for h in found_order if h in MEMO_HEADINGS]
    expected_present = [h for h in MEMO_HEADINGS if h in present]
    if present != expected_present:
        errors.append("Headings out of order")

    # Load problem file and extraction
    primary = None
    problem_ids = set()
    try:
        front = vp.parse_problem_md_front_matter(run_path / "02-problem.md")
        primary = front.get("primary_problem")
        problem_ids = vp.extract_problem_ids(front)
    except (FileNotFoundError, IOError, ValueError) as e:
        errors.append(str(e))
    extraction: dict = {}
    extraction_ids = set()
    try:
        extraction = vp.load_json_file(run_path / "01-extraction.json")
        extraction_ids, _ = vp.extract_extraction_ids(extraction)
    except (FileNotFoundError, ValueError) as e:
        errors.append(str(e))

    # Section 1 says "No PRD"
    if "No PRD" not in sections.get(MEMO_HEADINGS[0], ""):
        errors.append('Section 1: must state "No PRD"')

    # Section 2 cites the primary problem
    if primary and not re.search(rf'\b{re.escape(str(primary))}\b', sections.get(MEMO_HEADINGS[1], "")):
        errors.append(f"Section 2: must cite the primary problem {primary}")

    # Every citation exists
    known = extraction_ids | problem_ids | vp.load_evidence_ids(run_path) | vp.load_anecdote_ids(run_path)
    cited: List[str] = []
    for token in vp.ID_TOKEN_RE.findall(text):
        if token not in known and token not in cited:
            cited.append(token)
    for token in cited:
        errors.append(f"Citation not found in extraction or problem file: {token}")

    # Number tracing, sections 2 to 4
    supported = vp.collect_supported_numbers(extraction, run_path)
    literals = {run_path.name}
    if isinstance(extraction.get("run_id"), str):
        literals.add(extraction["run_id"])
    for index in (1, 2, 3):
        heading = MEMO_HEADINGS[index]
        for display, value in vp.traceable_numbers(sections.get(heading, ""), literals):
            if value not in supported:
                errors.append(f"Unsupported number '{display}' in section {index + 1}")

    # Section 4 has at least two list items
    items = [ln for ln in sections.get(MEMO_HEADINGS[3], "").split('\n') if vp.LIST_ITEM_RE.match(ln)]
    if len(items) < 2:
        errors.append("Section 4: needs at least two evidence items as a list")

    # No TODO / TBD / [[
    for match in re.finditer(r'\bTODO\b|\bTBD\b', text):
        errors.append(f"Found {match.group()} in memo text")
    if "[[" in text:
        errors.append("Found [[ placeholder in memo text")

    return errors


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python scripts/validate_memo.py <run_dir>")
        sys.exit(1)
    try:
        errors = validate_memo(sys.argv[1])
    except (OSError, ValueError) as e:
        print(str(e))
        sys.exit(1)
    for error in errors:
        print(error)
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
