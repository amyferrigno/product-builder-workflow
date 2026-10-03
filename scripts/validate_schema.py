#!/usr/bin/env python3
"""
Validator script for JSON Schema draft 2020-12.
Usage: python scripts/validate_schema.py <schema_file> <data_file>
"""

import sys
import json
import os

try:
    import yaml
    from jsonschema import Draft202012Validator
except ImportError as e:
    print(f"Error: Missing required module: {e}")
    sys.exit(1)


def load_json_or_yaml(file_path):
    """Load JSON or YAML file. Return data and format."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    try:
        with open(file_path, 'r') as f:
            content = f.read()
    except IOError as e:
        raise IOError(f"Cannot read file {file_path}: {e}")

    # Check if file is empty
    if not content or not content.strip():
        raise ValueError(f"Cannot parse {file_path}: file is empty")

    # Try JSON first
    try:
        return json.loads(content), "json"
    except json.JSONDecodeError:
        pass

    # Try YAML
    try:
        return yaml.safe_load(content), "yaml"
    except yaml.YAMLError as e:
        raise ValueError(f"Cannot parse {file_path} as JSON or YAML: {e}")


def validate(schema_path, data_path):
    """Validate data against schema. Return (is_valid, error_messages)."""

    # Load schema
    try:
        if not os.path.exists(schema_path):
            raise FileNotFoundError(f"Schema file not found: {schema_path}")
        with open(schema_path, 'r') as f:
            schema = json.load(f)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return False, []
    except json.JSONDecodeError as e:
        print(f"Error: Schema is not valid JSON: {e}")
        return False, []
    except IOError as e:
        print(f"Error: Cannot read schema file: {e}")
        return False, []

    # Load data
    try:
        data, _ = load_json_or_yaml(data_path)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return False, []
    except (ValueError, IOError) as e:
        print(f"Error: {e}")
        return False, []

    # Validate
    validator = Draft202012Validator(schema)
    errors = list(validator.iter_errors(data))

    return len(errors) == 0, errors


def main():
    if len(sys.argv) != 3:
        print("Usage: python scripts/validate_schema.py <schema_file> <data_file>")
        sys.exit(1)

    schema_path = sys.argv[1]
    data_path = sys.argv[2]

    is_valid, errors = validate(schema_path, data_path)

    if is_valid:
        sys.exit(0)

    # Print errors
    for error in errors:
        path = ".".join(str(p) for p in error.absolute_path) if error.absolute_path else "<root>"
        print(f"Error at {path}: {error.message}")

    sys.exit(1)


if __name__ == "__main__":
    main()
