#!/usr/bin/env python3
"""
Intake script: convert raw meeting notes into a numbered, citable source file.
Usage: python scripts/intake.py <path | -> [--slug name] [--date YYYY-MM-DD] [--runs-dir runs]
"""

import sys
import json
import hashlib
import argparse
import zipfile
import xml.etree.ElementTree as ET
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, Any


def hash_content(content: bytes) -> str:
    """Compute SHA256 hash of content bytes."""
    return hashlib.sha256(content).hexdigest()


def read_markdown_file(file_path: str) -> bytes:
    """Read a markdown file as bytes."""
    try:
        with open(file_path, 'rb') as f:
            return f.read()
    except (OSError, UnicodeDecodeError):
        raise ValueError(f"Cannot read {file_path}")


def read_text_file(file_path: str) -> bytes:
    """Read a text file as bytes."""
    try:
        with open(file_path, 'rb') as f:
            return f.read()
    except (OSError, UnicodeDecodeError):
        raise ValueError(f"Cannot read {file_path}")


def read_docx_file(file_path: str) -> str:
    """Read a DOCX file and extract text as string."""
    try:
        with zipfile.ZipFile(file_path, 'r') as docx:
            # Read word/document.xml
            try:
                xml_content = docx.read('word/document.xml')
            except KeyError:
                raise ValueError("Corrupt DOCX: missing word/document.xml")

            try:
                root = ET.fromstring(xml_content)
            except ET.ParseError:
                raise ValueError("Corrupt DOCX: invalid XML in document.xml")

            # Extract text from paragraphs
            # Namespace for Office Open XML
            namespaces = {
                'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
            }

            paragraphs = []
            for para in root.findall('.//w:p', namespaces):
                text_parts = []
                for text_elem in para.findall('.//w:t', namespaces):
                    if text_elem.text:
                        text_parts.append(text_elem.text)
                paragraphs.append(''.join(text_parts))

            return '\n'.join(paragraphs)
    except zipfile.BadZipFile:
        raise ValueError("Corrupt DOCX: not a valid zip file")


def read_from_stdin() -> bytes:
    """Read from stdin as bytes."""
    return sys.stdin.buffer.read()


def number_lines(content: str) -> str:
    """Number all lines of content. Preserve blank lines with their numbers."""
    if not content or not content.strip():
        return ''

    lines = content.split('\n')
    # Remove trailing newline if content ends with one
    if content.endswith('\n') and lines and lines[-1] == '':
        lines = lines[:-1]

    numbered = []
    for i, line in enumerate(lines, start=1):
        numbered.append(f"{i}: {line}")

    return '\n'.join(numbered)


def validate_slug(slug: str) -> bool:
    """Validate that slug matches ^[a-z0-9]+(-[a-z0-9]+)*$ (lowercase letters and digits separated by single hyphens)."""
    return bool(re.match(r'^[a-z0-9]+(-[a-z0-9]+)*$', slug))


def derive_slug(file_path: str) -> str:
    """Derive a slug from a file path."""
    filename = Path(file_path).stem
    # Convert to lowercase and replace spaces/underscores with hyphens
    slug = filename.lower().replace('_', '-').replace(' ', '-')
    # Remove consecutive hyphens
    while '--' in slug:
        slug = slug.replace('--', '-')
    return slug.strip('-')


def create_run_dir(run_id: str, runs_dir: str) -> str:
    """Create the run directory structure. Return the run directory path."""
    run_path = Path(runs_dir) / run_id

    # Check if already exists
    if run_path.exists():
        raise FileExistsError(f"Run directory already exists: {run_path}")

    # Create structure
    run_path.mkdir(parents=True, exist_ok=False)
    (run_path / "00-notes").mkdir(parents=True)
    (run_path / "approvals").mkdir(parents=True)

    return str(run_path)


def create_state_json(run_id: str, notes_hash: str) -> Dict[str, Any]:
    """Create the initial state.json object."""
    return {
        "run_id": run_id,
        "stage": "stage1",
        "status": "in_progress",
        "verdicts": {
            "prd": None,
            "ux": None
        },
        "artifact_hashes": {
            "notes": notes_hash
        },
        "approval_hashes": {
            "prd": None,
            "ux": None,
            "tickets": None
        },
        "jira_keys": {},
        "updated_at": datetime.utcnow().isoformat() + "Z"
    }


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Convert raw meeting notes into a numbered, citable source file."
    )
    parser.add_argument("input", help="Input file path or '-' for stdin")
    parser.add_argument("--slug", default=None, help="Slug for run ID (required for stdin)")
    parser.add_argument("--date", default=None, help="Date in YYYY-MM-DD format (default: today)")
    parser.add_argument("--runs-dir", default="runs", help="Directory for run folders (default: runs)")

    args = parser.parse_args()

    # Determine date
    if args.date:
        try:
            datetime.strptime(args.date, "%Y-%m-%d")
            date_str = args.date
        except ValueError:
            print("Error: Invalid date format. Expected YYYY-MM-DD", file=sys.stderr)
            sys.exit(1)
    else:
        date_str = datetime.now().strftime("%Y-%m-%d")

    # Read input
    raw_bytes = None
    text_content = None
    input_filename = None
    input_path_obj = None

    if args.input == "-":
        # Read from stdin
        if args.slug is None:
            print("Error: --slug is required when reading from stdin", file=sys.stderr)
            sys.exit(1)
        raw_bytes = read_from_stdin()
        slug = args.slug
        input_filename = "pasted.txt"
    else:
        # Read from file
        input_path_obj = Path(args.input)

        if not input_path_obj.exists():
            print("Error: File not found", file=sys.stderr)
            sys.exit(1)

        # Check extension
        ext = input_path_obj.suffix.lower()
        if ext == ".md":
            try:
                raw_bytes = read_markdown_file(args.input)
            except ValueError:
                print("Error: Cannot read file", file=sys.stderr)
                sys.exit(1)
        elif ext == ".txt":
            try:
                raw_bytes = read_text_file(args.input)
            except ValueError:
                print("Error: Cannot read file", file=sys.stderr)
                sys.exit(1)
        elif ext == ".docx":
            try:
                # For .docx, extract text then use original file bytes
                text_content = read_docx_file(args.input)
                with open(args.input, 'rb') as f:
                    raw_bytes = f.read()
            except ValueError:
                print("Error: Cannot read file", file=sys.stderr)
                sys.exit(1)
        else:
            print("Error: Unsupported file type", file=sys.stderr)
            sys.exit(1)

        input_filename = input_path_obj.name
        slug = args.slug if args.slug is not None else derive_slug(args.input)

    # Decode raw_bytes to get text content for numbering (unless already extracted from docx)
    if text_content is None:
        try:
            text_content = raw_bytes.decode('utf-8')
        except UnicodeDecodeError:
            print("Error: Cannot read file", file=sys.stderr)
            sys.exit(1)

    # Check for empty or whitespace-only content BEFORE creating run folder
    if not text_content or not text_content.strip():
        print("Error: input is empty", file=sys.stderr)
        sys.exit(1)

    # Validate slug format
    if not validate_slug(slug):
        print("Error: slug must match ^[a-z0-9]+(-[a-z0-9]+)*$ (lowercase letters and digits separated by single hyphens)", file=sys.stderr)
        sys.exit(1)

    # Create run ID and directory
    run_id = f"{date_str}-{slug}"

    try:
        run_dir = create_run_dir(run_id, args.runs_dir)
    except FileExistsError:
        print("Error: run already exists", file=sys.stderr)
        sys.exit(1)

    # Save raw file as bytes
    raw_file_path = Path(run_dir) / "00-notes" / input_filename
    try:
        with open(raw_file_path, 'wb') as f:
            f.write(raw_bytes)
    except IOError:
        print("Error: Cannot write file", file=sys.stderr)
        sys.exit(1)

    # Number the lines
    numbered_content = number_lines(text_content)

    # Save numbered file
    numbered_file_path = Path(run_dir) / "00-notes" / "notes.numbered.md"
    try:
        with open(numbered_file_path, 'w', encoding='utf-8') as f:
            f.write(numbered_content)
    except IOError:
        print("Error: Cannot write file", file=sys.stderr)
        sys.exit(1)

    # Create state.json with hash of raw bytes
    notes_hash = hash_content(raw_bytes)
    state_obj = create_state_json(run_id, notes_hash)

    state_file_path = Path(run_dir) / "state.json"
    try:
        with open(state_file_path, 'w', encoding='utf-8') as f:
            json.dump(state_obj, f, indent=2)
    except IOError:
        print("Error: Cannot write file", file=sys.stderr)
        sys.exit(1)

    # Validate state.json against schema
    try:
        from jsonschema import Draft202012Validator
    except ImportError:
        print("Error: Missing required module: jsonschema", file=sys.stderr)
        sys.exit(1)

    schema_path = Path(__file__).parent.parent / "schemas" / "state.schema.json"
    try:
        with open(schema_path, 'r') as f:
            schema = json.load(f)
    except FileNotFoundError:
        print("Error: Schema not found", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError:
        print("Error: Invalid schema", file=sys.stderr)
        sys.exit(1)

    validator = Draft202012Validator(schema)
    errors = list(validator.iter_errors(state_obj))
    if errors:
        print("Error: state.json validation failed", file=sys.stderr)
        sys.exit(1)

    # Make this the active run only when it lives in the repo's own runs/ folder
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import active_run
    if active_run.is_repo_run(run_dir):
        try:
            active_run.set_active(run_dir)
        except (ValueError, OSError):
            print("Warning: could not set the active run", file=sys.stderr)

    # Count lines
    if numbered_content:
        line_count = len(numbered_content.split('\n'))
    else:
        line_count = 0

    # Output summary as JSON
    summary = {
        "run_id": run_id,
        "run_dir": run_dir,
        "numbered_notes_path": str(numbered_file_path),
        "line_count": line_count
    }

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
