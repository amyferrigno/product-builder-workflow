#!/usr/bin/env python3
"""
Validate problem.md against schema and consistency rules.
Usage: python scripts/validate_problem.py <run_dir>
"""

import sys
import json
import re
from pathlib import Path
from typing import List, Tuple, Dict, Any

try:
    import yaml
    from jsonschema import Draft202012Validator
except ImportError as e:
    print(f"Error: Missing required module: {e}")
    sys.exit(1)

# Import compute_verdict from ai_gates
sys.path.insert(0, str(Path(__file__).parent))
from ai_gates import compute_verdict


def load_schema(schema_name: str, repo_root: Path) -> dict:
    """Load a schema file."""
    schema_path = repo_root / "schemas" / f"{schema_name}.schema.json"
    try:
        with open(schema_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        raise FileNotFoundError(f"Schema not found: {schema_path}")
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid schema {schema_path}: {e}")


def load_json_file(file_path: Path) -> dict:
    """Load a JSON file."""
    try:
        with open(file_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        raise FileNotFoundError(f"File not found: {file_path}")
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in {file_path}: {e}")


def parse_problem_md(problem_path: Path) -> Tuple[Dict[str, Any], str]:
    """
    Parse problem.md file.
    Returns (front_matter_dict, body_text).
    """
    try:
        with open(problem_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        raise FileNotFoundError(f"File not found: {problem_path}")
    except IOError as e:
        raise IOError(f"Cannot read file: {e}")

    # Extract front matter
    if not content.startswith('---'):
        raise ValueError("problem.md must start with --- (YAML front matter)")

    lines = content.split('\n')

    # Find closing ---
    end_idx = None
    for i in range(1, len(lines)):
        if lines[i] == '---':
            end_idx = i
            break

    if end_idx is None:
        raise ValueError("problem.md: missing closing --- for YAML front matter")

    # Parse front matter
    front_matter_text = '\n'.join(lines[1:end_idx])
    try:
        front_matter = yaml.safe_load(front_matter_text)
        if front_matter is None:
            front_matter = {}
        elif not isinstance(front_matter, dict):
            raise ValueError("front matter must be a mapping")
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML front matter: {e}")

    # Extract body
    body = '\n'.join(lines[end_idx + 1:])

    return front_matter, body


def extract_headings(text: str) -> dict:
    """Extract headings from markdown body."""
    headings = {}
    for line in text.split('\n'):
        if line.startswith('## '):
            heading = line[3:].strip()
            headings[heading] = True
    return headings




def validate_problem(run_dir: str) -> Tuple[bool, List[str]]:
    """
    Validate problem.md in run_dir.
    Returns (is_valid, error_messages).
    """
    run_path = Path(run_dir)
    errors = []

    if not run_path.is_dir():
        return False, [f"Run directory not found: {run_dir}"]

    # Find repo root by searching for schemas directory
    repo_root = run_path.parent.parent
    if not (repo_root / "schemas").exists():
        # Try current working directory
        repo_root = Path.cwd()
        if not (repo_root / "schemas").exists():
            # Try looking up from the script location
            repo_root = Path(__file__).parent.parent
            if not (repo_root / "schemas").exists():
                return False, ["Cannot find schemas directory"]

    # Check run_id matches folder name
    run_id = run_path.name

    # Parse problem.md
    problem_path = run_path / "02-problem.md"
    try:
        front_matter, body = parse_problem_md(problem_path)
    except (FileNotFoundError, IOError, ValueError) as e:
        return False, [str(e)]

    # Check run_id from front matter matches folder name
    fm_run_id = front_matter.get("run_id")
    if fm_run_id != run_id:
        errors.append(f"run_id mismatch: front matter has '{fm_run_id}', folder is '{run_id}'")

    # Validate front matter against schema
    try:
        schema = load_schema("problem", repo_root)
    except (FileNotFoundError, ValueError) as e:
        return False, [str(e)]

    validator = Draft202012Validator(schema)
    schema_errors = list(validator.iter_errors(front_matter))

    if schema_errors:
        for error in schema_errors:
            path = ".".join(str(p) for p in error.absolute_path) if error.absolute_path else "<root>"
            errors.append(f"Front matter error at {path}: {error.message}")
        return False, errors

    # Load extraction.json to check source_items
    extraction_path = run_path / "01-extraction.json"
    extraction = None
    try:
        extraction = load_json_file(extraction_path)
    except (FileNotFoundError, ValueError) as e:
        errors.append(str(e))

    # Collect all valid extraction IDs
    valid_ids = set()
    if extraction:
        for key in [
            "problems", "proposed_solutions", "user_segments", "requests",
            "decisions", "disagreements", "open_questions", "action_items", "metrics_mentioned"
        ]:
            for item in extraction.get(key, []):
                item_id = item.get("id")
                if item_id:
                    valid_ids.add(item_id)

    # Check problems exist and are valid
    problems = front_matter.get("problems", [])
    if not problems:
        errors.append("problems list is empty")

    # Check problem IDs are unique
    problem_ids = [p.get("id") for p in problems]
    if len(problem_ids) != len(set(problem_ids)):
        errors.append("Duplicate problem IDs found")

    # Check that all source_items reference valid extraction IDs
    for problem in problems:
        source_items = problem.get("source_items", [])
        for source_id in source_items:
            if source_id not in valid_ids:
                errors.append(f"Problem {problem.get('id')}: source_items references unknown ID '{source_id}'")

    # Check that UNVALIDATED problems list missing_evidence
    for problem in problems:
        if problem.get("validation_status") == "UNVALIDATED":
            missing_evidence = problem.get("missing_evidence", [])
            if not missing_evidence:
                errors.append(f"Problem {problem.get('id')}: UNVALIDATED but missing_evidence is empty")

    # Check that reframed_from_solution=true implies UNVALIDATED
    for problem in problems:
        if problem.get("reframed_from_solution") is True:
            if problem.get("validation_status") != "UNVALIDATED":
                errors.append(
                    f"Problem {problem.get('id')}: reframed_from_solution=true requires validation_status=UNVALIDATED"
                )

    # Check primary_problem exists in problems
    primary_problem = front_matter.get("primary_problem")
    if primary_problem:
        if primary_problem not in problem_ids:
            errors.append(f"primary_problem '{primary_problem}' not found in problems list")

    # Check parked_problems exist in problems
    parked_problems = front_matter.get("parked_problems", [])
    for parked_id in parked_problems:
        if parked_id not in problem_ids:
            errors.append(f"parked_problems '{parked_id}' not found in problems list")

    # Extract headings from body
    headings = extract_headings(body)

    # Check required headings
    required_headings = [
        "Problem statement",
        "Who has it",
        "Exact scenario",
        "Current workaround",
        "Why now",
        "Strategic fit",
        "Validation status",
        "Other topics parked"
    ]

    for heading in required_headings:
        if heading not in headings:
            errors.append(f"Missing required heading: '{heading}'")

    # Check that "Open questions" heading is present if there are disagreements in extraction
    if extraction:
        disagreements = extraction.get("disagreements", [])
        if disagreements and "Open questions" not in headings:
            errors.append("Disagreements found in extraction but 'Open questions' heading is missing")

    # Check AI decision heading
    ai_proposed = front_matter.get("ai", {}).get("proposed", False)
    if ai_proposed:
        if "AI decision" not in headings:
            errors.append("AI proposed=true but missing 'AI decision' heading")

    # Check AI verdict consistency
    ai_obj = front_matter.get("ai", {})
    if ai_proposed and "verdict" in ai_obj:
        gates = ai_obj.get("gates", {})
        red_flags = ai_obj.get("red_flags", [])

        # Extract result values from gates (handle both string and object formats)
        gate_results = {}
        for gate_num in ["1", "2", "3", "4", "5"]:
            gate_val = gates.get(gate_num)
            if isinstance(gate_val, dict):
                gate_results[gate_num] = gate_val.get("result")
            else:
                gate_results[gate_num] = gate_val

        try:
            computed_verdict = compute_verdict(gate_results, red_flags)
        except ValueError as e:
            errors.append(f"AI verdict computation error: {str(e)}")
            computed_verdict = None

        declared_verdict = ai_obj.get("verdict")

        if computed_verdict and computed_verdict != declared_verdict:
            errors.append(
                f"AI verdict mismatch: declared '{declared_verdict}' but gates/red_flags compute '{computed_verdict}'"
            )

    # Check for TODO/TBD text in both front matter and body (case-sensitive, whole words)
    todo_pattern = r'\bTODO\b'
    tbd_pattern = r'\bTBD\b'

    # Check front matter (convert to string)
    front_matter_text = '\n'.join(f"{k}: {v}" for k, v in front_matter.items())
    for line in front_matter_text.split('\n'):
        if re.search(todo_pattern, line):
            errors.append(f"Found TODO text in front matter: {line.strip()}")
        if re.search(tbd_pattern, line):
            errors.append(f"Found TBD text in front matter: {line.strip()}")

    # Check body
    body_lines = body.split('\n')
    for i, line in enumerate(body_lines, start=1):
        if re.search(todo_pattern, line):
            errors.append(f"Line {i}: Found TODO text: {line.strip()}")
        if re.search(tbd_pattern, line):
            errors.append(f"Line {i}: Found TBD text: {line.strip()}")

    return len(errors) == 0, errors


def main():
    """Main entry point."""
    if len(sys.argv) != 2:
        print("Usage: python scripts/validate_problem.py <run_dir>")
        sys.exit(1)

    run_dir = sys.argv[1]

    is_valid, errors = validate_problem(run_dir)

    for error in errors:
        print(error)

    sys.exit(0 if is_valid else 1)


if __name__ == "__main__":
    main()
