#!/usr/bin/env python3
"""
Validate prd.md against structure, consistency and traceability rules.
Usage: python scripts/validate_prd.py <run_dir>

Validation conventions:
  - Rule c: REQ and MET IDs must match ^REQ-\d{3}$ and ^MET-\d{3}$ exactly (3 digits)
  - Rule e: Metric IDs are defined as bold **MET-###** in section 8; section must contain
    the literal strings "Target:", "Timeframe:", "Guardrail", and "Baseline:"
"""

import sys
import json
import re
from pathlib import Path
from typing import List, Tuple, Dict, Any, Set, Optional

try:
    import yaml
except ImportError as e:
    print(f"Error: Missing required module: {e}")
    sys.exit(1)


# PRD headings (section 1-20)
PRD_HEADINGS = [
    "Header",
    "TL;DR",
    "Problem statement",
    "Why now and strategic fit",
    "Target users and segments",
    "Evidence",
    "Goals and non-goals",
    "Success metrics",
    "Value tests",
    "Solution overview",
    "User flow",
    "Requirements",
    "MVP scope",
    "Dependencies and assumptions",
    "Risks and mitigations",
    "Launch and rollout",
    "Open questions",
    "Alignment",
    "Decision log",
    "Traceability",
]

# PRD addendum headings (A1-A10) - only present if ai.proposed is true
ADDENDUM_HEADINGS = [
    "5-Gate verdict and red flag check",
    "AI pattern and architecture choice",
    "Context engineering",
    "What good looks like",
    "Constraints",
    "Error tolerance and fallback",
    "Trust, control, recovery",
    "Eval plan",
    "Observability",
    "Full cost estimate",
]


def load_json_file(file_path: Path) -> dict:
    """Load a JSON file, raise on error."""
    try:
        with open(file_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        raise FileNotFoundError(f"File not found: {file_path}")
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in {file_path}: {e}")


def parse_problem_md_front_matter(problem_path: Path) -> dict:
    """Parse problem.md and extract front matter dict."""
    try:
        with open(problem_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        raise FileNotFoundError(f"File not found: {problem_path}")
    except IOError as e:
        raise IOError(f"Cannot read file: {e}")

    if not content.startswith('---'):
        raise ValueError("problem.md must start with --- (YAML front matter)")

    lines = content.split('\n')
    end_idx = None
    for i in range(1, len(lines)):
        if lines[i] == '---':
            end_idx = i
            break

    if end_idx is None:
        raise ValueError("problem.md: missing closing --- for YAML front matter")

    front_matter_text = '\n'.join(lines[1:end_idx])
    try:
        front_matter = yaml.safe_load(front_matter_text)
        if front_matter is None:
            front_matter = {}
        elif not isinstance(front_matter, dict):
            raise ValueError("front matter must be a mapping")
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML front matter: {e}")

    return front_matter


def parse_prd_headings(prd_text: str) -> Dict[str, Tuple[int, int]]:
    """
    Extract all headings from PRD markdown.
    Returns dict: heading_text -> (line_num, level)
    level: 2 for ##, 3 for ###
    """
    headings = {}
    for i, line in enumerate(prd_text.split('\n'), start=1):
        if line.startswith('### '):
            text = line[4:].strip()
            headings[text] = (i, 3)
        elif line.startswith('## '):
            text = line[3:].strip()
            headings[text] = (i, 2)
    return headings


def extract_extraction_ids(extraction: dict) -> Tuple[Set[str], Set[str]]:
    """
    Extract all valid extraction item IDs from extraction.json.
    Returns (all_ids, prefixes_seen)
    """
    all_ids = set()
    prefixes = set()

    for key in [
        "problems", "proposed_solutions", "user_segments", "requests",
        "decisions", "disagreements", "open_questions", "action_items", "metrics_mentioned"
    ]:
        for item in extraction.get(key, []):
            item_id = item.get("id")
            if item_id:
                all_ids.add(item_id)
                # Extract prefix (e.g., "P" from "P-1")
                match = re.match(r'^([A-Za-z]+)-', item_id)
                if match:
                    prefixes.add(match.group(1))

    return all_ids, prefixes


def extract_problem_ids(front_matter: dict) -> Set[str]:
    """Extract all PB-# IDs from problem front matter."""
    pb_ids = set()
    problems = front_matter.get("problems", [])
    for problem in problems:
        pb_id = problem.get("id")
        if pb_id:
            pb_ids.add(pb_id)
    return pb_ids


def load_evidence_ids(run_dir: Path) -> Set[str]:
    """Load all evidence card IDs from 03-evidence/*.json."""
    evidence_ids = set()
    evidence_dir = run_dir / "03-evidence"

    if not evidence_dir.exists():
        return evidence_ids

    if evidence_dir.is_dir():
        for json_file in evidence_dir.glob("*.json"):
            try:
                card = load_json_file(json_file)
                ev_id = card.get("id")
                if ev_id:
                    evidence_ids.add(ev_id)
            except (FileNotFoundError, ValueError):
                pass

    return evidence_ids


def load_anecdote_ids(run_dir: Path) -> Set[str]:
    """Load all anecdote IDs from 04-anecdotes.json."""
    anecdote_ids = set()
    anecdotes_file = run_dir / "04-anecdotes.json"

    if not anecdotes_file.exists():
        return anecdote_ids

    try:
        data = load_json_file(anecdotes_file)
        # Handle both array and object with anecdotes array
        if isinstance(data, list):
            anecdotes = data
        elif isinstance(data, dict) and "anecdotes" in data:
            anecdotes = data["anecdotes"]
        else:
            anecdotes = []

        for anecdote in anecdotes:
            an_id = anecdote.get("id")
            if an_id:
                anecdote_ids.add(an_id)
    except (FileNotFoundError, ValueError):
        pass

    return anecdote_ids


def load_anecdote_quotes(run_dir: Path) -> Dict[str, str]:
    """Map each anecdote id in 04-anecdotes.json to its quote text."""
    anecdotes_file = run_dir / "04-anecdotes.json"
    if not anecdotes_file.exists():
        return {}
    try:
        data = load_json_file(anecdotes_file)
    except (FileNotFoundError, ValueError):
        return {}
    if isinstance(data, dict):
        data = data.get("anecdotes", [])
    if not isinstance(data, list):
        return {}
    return {
        r["id"]: r["quote"]
        for r in data
        if isinstance(r, dict) and isinstance(r.get("id"), str) and isinstance(r.get("quote"), str)
    }


def extraction_item_texts(extraction: dict) -> Dict[str, str]:
    """Map each extraction item id to its text."""
    texts: Dict[str, str] = {}
    if isinstance(extraction, dict):
        for value in extraction.values():
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict) and isinstance(item.get("id"), str) and isinstance(item.get("text"), str):
                        texts[item["id"]] = item["text"]
    return texts


# Quote styles: double (straight or curly, mixed pairs allowed), single (straight or curly,
# mixed pairs allowed; an opening single quote must not follow a word character and a closing one
# must not be followed by one, so don't and team's are not quote marks), guillemets in both
# directions, German low quotes, single angle quotes and CJK corner brackets.
QUOTED_RE = re.compile(
    '["\u201c]([^"\u201c\u201d]+)["\u201d]'
    "|(?<!\\w)['\u2018](?=\\S)(.+?)(?<=\\S)['\u2019](?!\\w)"
    "|\u00ab([^\u00bb]+)\u00bb"
    "|\u00bb([^\u00ab]+)\u00ab"
    "|\u201e([^\u201c\u201d]+)[\u201c\u201d]"
    "|\u2039([^\u203a]+)\u203a"
    "|\u300c([^\u300d]+)\u300d"
)
BLOCKQUOTE_RE = re.compile(r'^\s*>[>\s]*(.*)$')
CITATION_GROUP_RE = re.compile(r'[(\[][^()\[\]]*\b[A-Z]+-\d+\b[^()\[\]]*[)\]]')
QUOTE_CHARS = '"\'\u201c\u201d\u2018\u2019\u00ab\u00bb'
LIST_ITEM_RE = re.compile(r'^\s*(?:[-*+]|\d+[.)])\s')


def quote_units(section_6b: str) -> List[str]:
    """Split section 6b into paragraphs, list items and table rows."""
    units: List[str] = []
    current: List[str] = []

    def flush() -> None:
        if current:
            units.append('\n'.join(current))
            current.clear()

    for line in section_6b.split('\n'):
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            flush()
        elif split_table_row(line) is not None:
            flush()
            units.append(line)
        elif LIST_ITEM_RE.match(line):
            flush()
            current.append(line)
        else:
            current.append(line)
    flush()
    return units


def _quoted_passages(unit: str) -> List[str]:
    """Quoted passages in one unit: inline quotes, and whole blockquote lines."""
    passages: List[str] = []
    inline_lines: List[str] = []
    for line in unit.split('\n'):
        block = BLOCKQUOTE_RE.match(line)
        if block:
            text = CITATION_GROUP_RE.sub(' ', block.group(1))
            text = re.sub(r'\b[A-Z]+-\d+\b', ' ', text)
            passages.append(text.strip(' \t' + QUOTE_CHARS + '-\u2013\u2014:,;'))
        else:
            inline_lines.append(line)
    for match in QUOTED_RE.finditer('\n'.join(inline_lines)):
        passages.append(next(g for g in match.groups() if g is not None))
    return passages


def find_unsupported_quotes(
    section_6b: str, anecdote_quotes: Dict[str, str], item_texts: Dict[str, str]
) -> List[str]:
    """
    Return quoted passages of 4 or more words that are not a substring of the quote of a cited
    anecdote (AN-###) or the text of a cited extraction item in the same paragraph, list item
    or table row.
    """
    unsupported: List[str] = []
    for unit in quote_units(section_6b):
        cited = set(re.findall(r'\b[A-Z]+-\d+\b', unit))
        sources = [" ".join(anecdote_quotes[i].split()) for i in cited if i in anecdote_quotes]
        sources += [" ".join(item_texts[i].split()) for i in cited if i in item_texts]
        for passage in _quoted_passages(unit):
            quoted = " ".join(passage.split())
            if len(quoted.split()) < 4:
                continue
            if not any(quoted in source for source in sources) and quoted not in unsupported:
                unsupported.append(quoted)
    return unsupported


def remove_html_comments(text: str) -> str:
    """Remove HTML comments from text."""
    return re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL)


def split_table_row(line: str) -> Optional[List[str]]:
    """Return the cells of a markdown table row, or None if the line is not one.

    Leading and trailing pipes are optional in GitHub tables, so any line
    containing a pipe counts as a row.
    """
    stripped = line.strip()
    if '|' not in stripped:
        return None
    if stripped.startswith('|'):
        stripped = stripped[1:]
    if stripped.endswith('|'):
        stripped = stripped[:-1]
    return [cell.strip() for cell in stripped.split('|')]


def find_section_content(prd_text: str, section_num: int) -> str:
    """Extract content between section N and section N+1 (or end of doc)."""
    lines = prd_text.split('\n')
    start_pattern = f"## {section_num}. "
    end_pattern = None
    if section_num < 20:
        end_pattern = f"## {section_num + 1}. "
    else:
        # After section 20, look for ## A1.
        end_pattern = "## A1. "

    start_idx = None
    end_idx = None

    for i, line in enumerate(lines):
        if line.startswith(start_pattern):
            start_idx = i
        if end_pattern and start_idx is not None and line.startswith(end_pattern):
            end_idx = i
            break

    if start_idx is None:
        return ""

    if end_idx is None:
        end_idx = len(lines)

    return '\n'.join(lines[start_idx:end_idx])


def parse_requirements(prd_text: str) -> List[Tuple[str, str]]:
    """Return (REQ id, priority) for each requirement row of section 12, in order.

    A row is a table row whose first cell holds a REQ id; the priority is the
    third cell (empty string when the row is too short).
    """
    rows: List[Tuple[str, str]] = []
    section = find_section_content(remove_html_comments(prd_text), 12)
    for line in section.split('\n'):
        cells = split_table_row(line)
        if not cells:
            continue
        match = re.search(r'REQ-\d{3}', cells[0])
        if match:
            rows.append((match.group(), cells[2] if len(cells) > 2 else ''))
    return rows


ID_TOKEN_RE = re.compile(r'\b[A-Z]+-\d+\b')
ISO_DATE_RE = re.compile(r'\b\d{4}-\d{2}-\d{2}\b')
THOUSANDS_RE = re.compile(r'\d{1,3}(?:,\d{3})+')
# Digits glued to a letter (M3, Q4, v2) are labels, not quantities.
NUMBER_RE = re.compile(r'(?<![A-Za-z\d.])(\d+(?:\.\d+)?)([%+]?)')


def _norm_number(raw: str) -> float:
    """Normalise a numeric string so 3.0 equals 3."""
    return round(float(raw), 6)


def _strip_ids_and_dates(text: str, literals: Set[str]) -> str:
    for literal in literals:
        if literal:
            text = text.replace(literal, ' ')
    text = ISO_DATE_RE.sub(' ', text)
    text = ID_TOKEN_RE.sub(' ', text)
    return THOUSANDS_RE.sub(lambda m: m.group().replace(',', ''), text)


def numeric_tokens(text: str, literals: Optional[Set[str]] = None) -> List[Tuple[str, float]]:
    """Return (display, normalised value) for each numeric token in text."""
    cleaned = _strip_ids_and_dates(text, literals or set())
    return [
        (m.group(1) + m.group(2), _norm_number(m.group(1)))
        for m in NUMBER_RE.finditer(cleaned)
    ]


def traceable_numbers(section_text: str, literals: Set[str]) -> List[Tuple[str, float]]:
    """Numeric tokens in a PRD section that need support, skipping structural lines."""
    tokens: List[Tuple[str, float]] = []
    for line in section_text.split('\n'):
        stripped = line.strip()
        if stripped.startswith('#'):
            continue
        if stripped and re.fullmatch(r'[|\s:\-]+', stripped):
            continue
        line = re.sub(r'^\s*\d+\.\s+', '', line)
        tokens.extend(numeric_tokens(line, literals))
    return tokens


def collect_supported_numbers(extraction: dict, run_path: Path) -> Set[float]:
    """Numbers backed by extraction item text and evidence cards."""
    supported: Set[float] = set()
    for items in extraction.values():
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                supported.update(v for _, v in numeric_tokens(item["text"]))

    evidence_dir = run_path / "03-evidence"
    if evidence_dir.is_dir():
        for json_file in evidence_dir.glob("*.json"):
            try:
                card = load_json_file(json_file)
            except (FileNotFoundError, ValueError):
                continue
            if not isinstance(card, dict):
                continue
            for field in ("value", "n"):
                raw = card.get(field)
                if isinstance(raw, (int, float)) and not isinstance(raw, bool):
                    supported.add(_norm_number(str(raw)))
                    if field == "value" and 0 < raw < 1:
                        supported.add(_norm_number(str(raw * 100)))
            for field in ("claim", "period"):
                raw = card.get(field)
                if isinstance(raw, str):
                    supported.update(v for _, v in numeric_tokens(raw))
    return supported


def validate_prd(run_dir: str) -> Tuple[bool, List[str]]:
    """
    Validate prd.md in run_dir.
    Returns (is_valid, error_messages).
    """
    run_path = Path(run_dir)
    errors = []

    if not run_path.is_dir():
        return False, [f"Run directory not found: {run_dir}"]

    # Load input files
    prd_path = run_path / "prd.md"
    problem_path = run_path / "02-problem.md"
    extraction_path = run_path / "01-extraction.json"

    # Check if prd.md exists and is readable
    if not prd_path.exists():
        return False, ["prd.md not found"]

    try:
        with open(prd_path, 'r', encoding='utf-8') as f:
            prd_text = f.read()
    except IOError as e:
        return False, [f"Cannot read prd.md: {e}"]

    # Load problem front matter to check ai.proposed
    ai_proposed = False
    try:
        front_matter = parse_problem_md_front_matter(problem_path)
        ai_obj = front_matter.get("ai", {})
        ai_proposed = ai_obj.get("proposed", False)
    except (FileNotFoundError, IOError, ValueError):
        # If problem.md is missing or invalid, assume ai.proposed = false
        # (we'll report the missing file separately below if critical)
        pass

    # Load extraction
    extraction = None
    extraction_ids = set()
    extraction_prefixes = set()
    try:
        extraction = load_json_file(extraction_path)
        extraction_ids, extraction_prefixes = extract_extraction_ids(extraction)
    except (FileNotFoundError, ValueError) as e:
        errors.append(str(e))
        extraction = {}
        extraction_ids = set()
        extraction_prefixes = set()

    # Load extraction problems for PB-# validation
    pb_ids = extract_problem_ids(front_matter) if 'front_matter' in locals() else set()

    # Load evidence and anecdote IDs
    evidence_ids = load_evidence_ids(run_path)
    anecdote_ids = load_anecdote_ids(run_path)

    # Check if evidence and anecdote providers are configured
    evidence_configured = len(evidence_ids) > 0
    anecdotes_configured = len(anecdote_ids) > 0

    # === Rule a: All 20 headings present, in order ===
    headings = parse_prd_headings(prd_text)

    # Check all 20 main headings
    heading_lines = []
    for i, heading_name in enumerate(PRD_HEADINGS, start=1):
        prd_heading = f"{i}. {heading_name}"
        if prd_heading in headings:
            heading_lines.append((i, headings[prd_heading][0]))
        else:
            errors.append(f"Missing heading: ## {prd_heading}")

    # Check heading order
    heading_lines.sort(key=lambda x: x[1])
    for i, (expected_num, line_num) in enumerate(heading_lines, start=1):
        if expected_num != i:
            errors.append(f"Headings out of order: section {expected_num} is not in position {i}")

    # Check section 6 sub-headings
    section_6_text = find_section_content(prd_text, 6)
    if section_6_text:
        section_6_headings = parse_prd_headings(section_6_text)
        for sub_num, sub_title in enumerate(["Data insights", "Customer anecdotes", "Evidence gaps"], start=1):
            sub_heading = f"6{chr(96+sub_num)}. {sub_title}"  # 6a, 6b, 6c
            if sub_heading not in section_6_headings:
                errors.append(f"Missing sub-heading: ### {sub_heading}")

    # === Rule b: Addendum headings present iff ai.proposed is true ===
    addendum_found = []
    for i, heading_name in enumerate(ADDENDUM_HEADINGS, start=1):
        addendum_heading = f"A{i}. {heading_name}"
        if addendum_heading in headings:
            addendum_found.append(addendum_heading)

    if ai_proposed:
        # All addendum headings must be present
        for i, heading_name in enumerate(ADDENDUM_HEADINGS, start=1):
            addendum_heading = f"A{i}. {heading_name}"
            if addendum_heading not in headings:
                errors.append(f"ai.proposed is true but missing addendum heading: ## {addendum_heading}")
    else:
        # No addendum headings should be present
        for heading in addendum_found:
            errors.append(f"ai.proposed is false but addendum heading present: ## {heading}")

    # === Rule c: REQ and MET IDs are unique and well-formed ===
    req_pattern = re.compile(r'\bREQ-\d{3}\b')
    met_pattern = re.compile(r'\bMET-\d{3}\b')

    # Remove HTML comments before checking
    prd_text_no_comments = remove_html_comments(prd_text)

    req_ids = set()
    met_ids = set()

    # Check for duplicate REQs in section 12 (requirements table rows only)
    section_12_text_for_dup = find_section_content(prd_text_no_comments, 12)
    req_id_count = {}
    if section_12_text_for_dup:
        # Only the FIRST cell of a requirements-table row defines a REQ
        for line in section_12_text_for_dup.split('\n'):
            cells = split_table_row(line)
            if not cells:
                continue
            match = req_pattern.search(cells[0])
            if match:
                req_id = match.group()
                req_id_count[req_id] = req_id_count.get(req_id, 0) + 1
                req_ids.add(req_id)

    for req_id, count in req_id_count.items():
        if count > 1:
            errors.append(f"Duplicate requirement ID: {req_id}")

    # Every REQ cited anywhere must be defined by a row in section 12
    for cited in sorted(set(req_pattern.findall(prd_text_no_comments)) - req_ids):
        errors.append(f"Requirement {cited} is cited but has no row in section 12")

    # Check for duplicate METs in section 8 (metrics table rows only)
    section_8_text_for_dup = find_section_content(prd_text_no_comments, 8)
    met_id_count = {}
    if section_8_text_for_dup:
        # Only check table rows (lines starting with |)
        for line in section_8_text_for_dup.split('\n'):
            if line.startswith('|') and 'MET-' in line:
                # Count occurrences of MET-IDs in this row
                for match in met_pattern.finditer(line):
                    met_id = match.group()
                    met_id_count[met_id] = met_id_count.get(met_id, 0) + 1
                    met_ids.add(met_id)

    for met_id, count in met_id_count.items():
        if count > 1:
            errors.append(f"Duplicate metric ID: {met_id}")

    # Also collect REQ and MET IDs from entire document for other validation
    for match in req_pattern.finditer(prd_text_no_comments):
        req_ids.add(match.group())
    for match in met_pattern.finditer(prd_text_no_comments):
        met_ids.add(match.group())

    # Check for malformed IDs
    bad_req_pattern = re.compile(r'\bREQ-\d{1,2}\b|\bREQ-\d{4,}\b')
    bad_met_pattern = re.compile(r'\bMET-\d{1,2}\b|\bMET-\d{4,}\b')

    for match in bad_req_pattern.finditer(prd_text_no_comments):
        errors.append(f"Malformed requirement ID: {match.group()}")

    for match in bad_met_pattern.finditer(prd_text_no_comments):
        errors.append(f"Malformed metric ID: {match.group()}")

    # === Rule d: Requirements table in section 12 ===
    section_12_text = find_section_content(prd_text, 12)
    if section_12_text:
        # Find requirement rows: table rows whose first cell holds a REQ id
        table_rows = []
        for line in section_12_text.split('\n'):
            row_cells = split_table_row(line)
            if row_cells and re.search(r'REQ-\d{3}', row_cells[0]):
                table_rows.append(row_cells)

        if not table_rows:
            errors.append("Section 12: no requirement rows found")

        for cells in table_rows:
            req_match = re.search(r'REQ-\d{3}', cells[0])
            req_id = req_match.group() if req_match else None

            if len(cells) < 4:
                errors.append(f"Requirement {req_id}: row has {len(cells)} cells, expected at least 4")
                continue

            priority_cell = cells[2]
            acceptance_cell = cells[3]

            # Priority check
            if priority_cell not in ['Must', 'Should', 'Could']:
                errors.append(f"Requirement {req_id}: priority must be Must, Should, or Could, got '{priority_cell}'")

            # Acceptance criteria check (must contain Given, When, Then)
            acceptance_lower = acceptance_cell.lower()
            missing = [
                word for word in ('Given', 'When', 'Then')
                if word.lower() not in acceptance_lower
            ]
            if missing:
                errors.append(f"Requirement {req_id}: acceptance criteria missing: {', '.join(missing)}")

    # === Rule e: Section 8 has exactly one primary metric with target and timeframe ===
    section_8_text = find_section_content(prd_text, 8)
    if section_8_text:
        section_8_no_comments = remove_html_comments(section_8_text)

        # Count "Primary metric" mentions
        primary_metric_matches = list(re.finditer(r'Primary metric', section_8_no_comments, re.IGNORECASE))

        if len(primary_metric_matches) == 0:
            errors.append("Section 8: no primary metric found")
        elif len(primary_metric_matches) > 1:
            errors.append(f"Section 8: found {len(primary_metric_matches)} primary metrics, expected exactly 1")

        # Check for Target:, Timeframe:, Guardrail, Baseline:
        if 'Target:' not in section_8_text:
            errors.append("Section 8: missing 'Target:' label")
        if 'Timeframe:' not in section_8_text:
            errors.append("Section 8: missing 'Timeframe:' label")
        if 'Guardrail' not in section_8_text:
            errors.append("Section 8: missing 'Guardrail' label")
        if 'Baseline:' not in section_8_text:
            errors.append("Section 8: missing 'Baseline:' label")

        # Validate Target: and Timeframe: have content after them
        target_match = re.search(r'Target:\s*(.+?)(?=\n|Target:|Timeframe:|$)', section_8_text, re.DOTALL)
        if target_match:
            target_content = target_match.group(1).strip()
            if not target_content:
                errors.append("Section 8: 'Target:' has no content")

        timeframe_match = re.search(r'Timeframe:\s*(.+?)(?=\n|Target:|Timeframe:|$)', section_8_text, re.DOTALL)
        if timeframe_match:
            timeframe_content = timeframe_match.group(1).strip()
            if not timeframe_content:
                errors.append("Section 8: 'Timeframe:' has no content")

    # === Rule f: Citations to EV-### and AN-### ===
    ev_pattern = re.compile(r'\bEV-\d{3}\b')
    an_pattern = re.compile(r'\bAN-\d{3}\b')

    for match in ev_pattern.finditer(prd_text_no_comments):
        ev_id = match.group()
        if ev_id not in evidence_ids:
            if not evidence_configured:
                # Check that section 6a contains "No data provider configured"
                pass  # Will check below
            errors.append(f"Evidence card cited but not found: {ev_id}")

    for match in an_pattern.finditer(prd_text_no_comments):
        an_id = match.group()
        if an_id not in anecdote_ids:
            if not anecdotes_configured:
                # Check that section 6b contains "No anecdote provider configured"
                pass  # Will check below
            errors.append(f"Anecdote cited but not found: {an_id}")

    # Check "No data provider configured" statement in section 6a
    if not evidence_configured and list(ev_pattern.finditer(prd_text_no_comments)):
        if "No data provider configured" not in prd_text:
            errors.append("Section 6a: evidence citations exist but 'No data provider configured' statement missing")

    if not evidence_configured and not list(ev_pattern.finditer(prd_text_no_comments)):
        section_6a_text = find_section_content(prd_text, 6)
        if section_6a_text and "Data insights" in section_6a_text:
            # Extract 6a section
            section_6a_lines = section_6a_text.split('\n')
            section_6a_start = None
            section_6a_end = None
            for i, line in enumerate(section_6a_lines):
                if '### 6a. Data insights' in line:
                    section_6a_start = i
                elif section_6a_start is not None and line.startswith('###'):
                    section_6a_end = i
                    break
            if section_6a_start is not None:
                if section_6a_end is None:
                    section_6a_end = len(section_6a_lines)
                section_6a_content = '\n'.join(section_6a_lines[section_6a_start:section_6a_end])
                if "No data provider configured" not in section_6a_content:
                    errors.append("Section 6a: no evidence cards and no 'No data provider configured' statement")

    if not anecdotes_configured and not list(an_pattern.finditer(prd_text_no_comments)):
        section_6_text = find_section_content(prd_text, 6)
        if section_6_text and "Customer anecdotes" in section_6_text:
            section_6_lines = section_6_text.split('\n')
            section_6b_start = None
            section_6b_end = None
            for i, line in enumerate(section_6_lines):
                if '### 6b. Customer anecdotes' in line:
                    section_6b_start = i
                elif section_6b_start is not None and line.startswith('###'):
                    section_6b_end = i
                    break
            if section_6b_start is not None:
                if section_6b_end is None:
                    section_6b_end = len(section_6_lines)
                section_6b_content = '\n'.join(section_6_lines[section_6b_start:section_6b_end])
                if "No anecdote provider configured" not in section_6b_content:
                    errors.append("Section 6b: no anecdotes and no 'No anecdote provider configured' statement")

    # === Rule g: Extraction IDs cited in parentheses or brackets ===
    # Every ID token inside each parenthesised or bracketed group is checked,
    # whatever the separator (comma, space, slash, semicolon, "and").
    group_pattern = re.compile(r'[(\[]([^()\[\]\n]*)[)\]]')
    id_token_pattern = re.compile(r'\b[A-Z]+-\d+\b')

    for group_match in group_pattern.finditer(prd_text_no_comments):
        for token_match in id_token_pattern.finditer(group_match.group(1)):
            id_token = token_match.group()

            # Skip REQ, MET, EV, AN, PB, SCR (checked by their own rules)
            if any(id_token.startswith(prefix) for prefix in ['REQ-', 'MET-', 'EV-', 'AN-', 'PB-', 'SCR-']):
                continue

            prefix = id_token.split('-')[0]
            if prefix not in extraction_prefixes:
                errors.append(f"Unknown extraction ID prefix in citation: {id_token}")
            elif id_token not in extraction_ids:
                errors.append(f"Extraction ID cited but not found: {id_token}")

    # === Rule g: PB-# tokens must exist in problem front matter ===
    pb_pattern = re.compile(r'\bPB-\d+\b')
    for match in pb_pattern.finditer(prd_text_no_comments):
        pb_id = match.group()
        if pb_id not in pb_ids:
            errors.append(f"Problem ID cited but not found in problems: {pb_id}")

    # === Rule h: Section 7 must contain "Non-goals" and a list ===
    section_7_text = find_section_content(prd_text, 7)
    if section_7_text:
        section_7_no_comments = remove_html_comments(section_7_text)
        if "Non-goals" not in section_7_no_comments:
            errors.append("Section 7: missing 'Non-goals' label")
        else:
            # Check for list items after "Non-goals"
            lines = section_7_no_comments.split('\n')
            non_goals_idx = None
            for i, line in enumerate(lines):
                if "Non-goals" in line:
                    non_goals_idx = i
                    break

            if non_goals_idx is not None:
                has_list = False
                for line in lines[non_goals_idx + 1:]:
                    if re.match(r'^\s*[-*]\s+', line):
                        has_list = True
                        break
                if not has_list:
                    errors.append("Section 7: 'Non-goals' label found but no list items following")

    # === Rule h: Section 13 must contain "Out of v1" and a list ===
    section_13_text = find_section_content(prd_text, 13)
    if section_13_text:
        section_13_no_comments = remove_html_comments(section_13_text)
        if not re.search(r'Out of v1', section_13_no_comments, re.IGNORECASE):
            errors.append("Section 13: missing 'Out of v1' label")
        else:
            # Check for list items after "Out of v1"
            lines = section_13_no_comments.split('\n')
            out_of_v1_idx = None
            for i, line in enumerate(lines):
                if re.search(r'Out of v1', line, re.IGNORECASE):
                    out_of_v1_idx = i
                    break

            if out_of_v1_idx is not None:
                has_list = False
                for line in lines[out_of_v1_idx + 1:]:
                    if re.match(r'^\s*[-*]\s+', line):
                        has_list = True
                        break
                if not has_list:
                    errors.append("Section 13: 'Out of v1' label found but no list items following")

    # === Rule i: No TODO or TBD outside HTML comments ===
    for match in re.finditer(r'\bTODO\b|\bTBD\b', prd_text_no_comments):
        token = match.group()
        errors.append(f"Found {token} in PRD text")

    # === Rule j: Number tracing ===
    supported_numbers = collect_supported_numbers(extraction or {}, run_path)
    run_id_literals = {run_path.name}
    if extraction and isinstance(extraction.get("run_id"), str):
        run_id_literals.add(extraction["run_id"])

    for section_num in (2, 3, 6):
        section_text = find_section_content(prd_text, section_num)
        if not section_text:
            continue
        for display, value in traceable_numbers(remove_html_comments(section_text), run_id_literals):
            if value not in supported_numbers:
                errors.append(f"Unsupported number '{display}' in section {section_num}")

    # === Rule k: Quotes in section 6b must come from an anecdote record or an extraction item ===
    section_6_text = find_section_content(prd_text, 6)
    if section_6_text:
        section_6b_lines = []
        in_6b = False
        for line in remove_html_comments(section_6_text).split('\n'):
            if line.startswith('### 6b.'):
                in_6b = True
            elif line.startswith('###'):
                in_6b = False
            if in_6b:
                section_6b_lines.append(line)
        for quoted in find_unsupported_quotes(
            '\n'.join(section_6b_lines), load_anecdote_quotes(run_path), extraction_item_texts(extraction or {})
        ):
            errors.append(f'Unsupported quote in section 6b: "{quoted[:40]}..."')

    return len(errors) == 0, errors


def main():
    """Main entry point."""
    if len(sys.argv) != 2:
        print("Usage: python scripts/validate_prd.py <run_dir>")
        sys.exit(1)

    run_dir = sys.argv[1]

    try:
        is_valid, errors = validate_prd(run_dir)
    except (FileNotFoundError, IOError, ValueError) as e:
        # One-line error with exit 1, no traceback
        print(str(e))
        sys.exit(1)

    for error in errors:
        print(error)

    sys.exit(0 if is_valid else 1)


if __name__ == "__main__":
    main()
