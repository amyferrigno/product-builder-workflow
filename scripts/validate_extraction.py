#!/usr/bin/env python3
"""
Validate extraction.json against schema and consistency rules.
Usage: python scripts/validate_extraction.py <run_dir>
"""

import sys
import json
from pathlib import Path
from typing import List, Tuple

try:
    from jsonschema import Draft202012Validator
except ImportError as e:
    print(f"Error: Missing required module: {e}")
    sys.exit(1)


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


def load_numbered_notes(notes_path: Path) -> dict:
    """Load numbered notes and return dict of {line_num: is_blank}."""
    try:
        with open(notes_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        raise FileNotFoundError(f"Numbered notes not found: {notes_path}")
    except IOError as e:
        raise IOError(f"Cannot read numbered notes: {e}")

    if not content or not content.strip():
        return {}

    line_info = {}
    for line in content.split('\n'):
        # Parse line number from "<n>: <text>" format
        try:
            parts = line.split(':', 1)
            if parts[0].strip().isdigit():
                line_num = int(parts[0].strip())
                # Check if the part after ": " is blank or whitespace
                text_part = parts[1][1:] if len(parts) > 1 else ""  # Skip the space after colon
                is_blank = not text_part or not text_part.strip()
                line_info[line_num] = is_blank
        except (ValueError, IndexError):
            pass

    return line_info


def validate_extraction(run_dir: str) -> Tuple[bool, List[str]]:
    """
    Validate extraction.json in run_dir.
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

    # Load extraction.json
    extraction_path = run_path / "01-extraction.json"
    try:
        extraction = load_json_file(extraction_path)
    except (FileNotFoundError, ValueError) as e:
        return False, [str(e)]

    # Validate against schema
    try:
        schema = load_schema("extraction", repo_root)
    except (FileNotFoundError, ValueError) as e:
        return False, [str(e)]

    validator = Draft202012Validator(schema)
    schema_errors = list(validator.iter_errors(extraction))

    if schema_errors:
        for error in schema_errors:
            path = ".".join(str(p) for p in error.absolute_path) if error.absolute_path else "<root>"
            errors.append(f"Schema error at {path}: {error.message}")
        return False, errors

    # Check run_id matches folder
    run_id = Path(run_dir).name
    extraction_run_id = extraction.get("run_id")
    if extraction_run_id != run_id:
        errors.append(f"run_id mismatch: extraction has '{extraction_run_id}', folder is '{run_id}'")

    # Load numbered notes
    notes_path = run_path / "00-notes" / "notes.numbered.md"
    try:
        line_info = load_numbered_notes(notes_path)
    except (FileNotFoundError, IOError) as e:
        errors.append(str(e))
        return False, errors

    # Check IDs are unique and source_lines are valid
    all_ids = []

    # Helper function to check an item list
    def check_items(items: List[dict], item_type: str) -> None:
        for item in items:
            item_id = item.get("id")
            if item_id:
                all_ids.append(item_id)

            source_lines = item.get("source_lines", [])
            for line_num in source_lines:
                if line_num not in line_info:
                    errors.append(
                        f"{item_type} {item_id}: source_lines contains {line_num} which doesn't exist in notes"
                    )
                elif line_info[line_num]:
                    errors.append(
                        f"{item_id}: cites blank line {line_num}"
                    )

    # Check all item types
    for key in [
        "problems", "proposed_solutions", "user_segments", "requests",
        "decisions", "disagreements", "open_questions", "action_items", "metrics_mentioned"
    ]:
        items = extraction.get(key, [])
        check_items(items, key.rstrip('s'))

    # Check for duplicate IDs
    seen_ids = set()
    for item_id in all_ids:
        if item_id in seen_ids:
            errors.append(f"Duplicate ID: {item_id}")
        seen_ids.add(item_id)

    return len(errors) == 0, errors


def main():
    """Main entry point."""
    if len(sys.argv) != 2:
        print("Usage: python scripts/validate_extraction.py <run_dir>")
        sys.exit(1)

    run_dir = sys.argv[1]

    is_valid, errors = validate_extraction(run_dir)

    for error in errors:
        print(error)

    sys.exit(0 if is_valid else 1)


if __name__ == "__main__":
    main()
