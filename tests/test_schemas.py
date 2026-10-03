"""Test that schemas are valid and samples validate correctly."""

import json
import yaml
from pathlib import Path
from jsonschema import Draft202012Validator


def load_schema(schema_name):
    """Load a schema from the schemas directory."""
    repo_root = Path(__file__).parent.parent
    schema_path = repo_root / "schemas" / f"{schema_name}.schema.json"
    with open(schema_path) as f:
        return json.load(f)


def load_sample(sample_path):
    """Load a JSON sample file."""
    with open(sample_path) as f:
        return json.load(f)


def test_all_schemas_are_valid():
    """Check that all schema files are valid JSON Schema draft 2020-12."""
    schema_names = [
        "pm-config",
        "registry",
        "extraction",
        "problem",
        "evidence",
        "anecdote",
        "provider-io",
        "ticket-manifest",
        "state",
    ]

    for schema_name in schema_names:
        schema = load_schema(schema_name)
        # If we can create a validator without error, the schema is valid
        try:
            Draft202012Validator.check_schema(schema)
        except Exception as e:
            raise AssertionError(f"Schema {schema_name} is not valid: {e}")


def test_valid_extraction_passes():
    """Check that valid extraction sample passes validation."""
    schema = load_schema("extraction")
    repo_root = Path(__file__).parent.parent
    sample_path = repo_root / "tests" / "samples" / "valid" / "extraction.json"
    data = load_sample(sample_path)

    validator = Draft202012Validator(schema)
    errors = list(validator.iter_errors(data))
    assert len(errors) == 0, f"Valid sample should pass: {[e.message for e in errors]}"


def test_invalid_extraction_fails():
    """Check that extraction with missing source_lines fails."""
    schema = load_schema("extraction")
    repo_root = Path(__file__).parent.parent
    sample_path = repo_root / "tests" / "samples" / "invalid" / "extraction-no-source-lines.json"
    data = load_sample(sample_path)

    validator = Draft202012Validator(schema)
    errors = list(validator.iter_errors(data))
    assert len(errors) > 0, "Invalid sample should fail validation"
    # Check that there's an error at problems.0 with message containing source_lines
    error_at_problems = any(
        ".".join(str(p) for p in e.absolute_path) == "problems.0" and
        "source_lines" in e.message
        for e in errors
    )
    assert error_at_problems, f"Expected error at problems.0 containing source_lines, got: {[(e.absolute_path, e.message) for e in errors]}"


def test_valid_evidence_passes():
    """Check that valid evidence sample passes validation."""
    schema = load_schema("evidence")
    repo_root = Path(__file__).parent.parent
    sample_path = repo_root / "tests" / "samples" / "valid" / "evidence.json"
    data = load_sample(sample_path)

    validator = Draft202012Validator(schema)
    errors = list(validator.iter_errors(data))
    assert len(errors) == 0, f"Valid sample should pass: {[e.message for e in errors]}"


def test_invalid_evidence_bad_id_fails():
    """Check that evidence with bad ID fails."""
    schema = load_schema("evidence")
    repo_root = Path(__file__).parent.parent
    sample_path = repo_root / "tests" / "samples" / "invalid" / "evidence-bad-id.json"
    data = load_sample(sample_path)

    validator = Draft202012Validator(schema)
    errors = list(validator.iter_errors(data))
    assert len(errors) > 0, "Invalid sample should fail validation"
    # Check that there's an error at id with validator pattern
    error_at_id = any(
        ".".join(str(p) for p in e.absolute_path) == "id" and
        e.validator == "pattern"
        for e in errors
    )
    assert error_at_id, f"Expected error at id with validator pattern, got: {[(e.absolute_path, e.validator, e.message) for e in errors]}"


def test_valid_anecdote_passes():
    """Check that valid anecdote sample passes validation."""
    schema = load_schema("anecdote")
    repo_root = Path(__file__).parent.parent
    sample_path = repo_root / "tests" / "samples" / "valid" / "anecdote.json"
    data = load_sample(sample_path)

    validator = Draft202012Validator(schema)
    errors = list(validator.iter_errors(data))
    assert len(errors) == 0, f"Valid sample should pass: {[e.message for e in errors]}"


def test_invalid_anecdote_quote_too_long_fails():
    """Check that anecdote with quote over 400 chars fails."""
    schema = load_schema("anecdote")
    repo_root = Path(__file__).parent.parent
    sample_path = repo_root / "tests" / "samples" / "invalid" / "anecdote-quote-too-long.json"
    data = load_sample(sample_path)

    validator = Draft202012Validator(schema)
    errors = list(validator.iter_errors(data))
    assert len(errors) > 0, "Invalid sample should fail validation"
    # Check that there's an error at quote with validator maxLength
    error_at_quote = any(
        ".".join(str(p) for p in e.absolute_path) == "quote" and
        e.validator == "maxLength"
        for e in errors
    )
    assert error_at_quote, f"Expected error at quote with validator maxLength, got: {[(e.absolute_path, e.validator, e.message) for e in errors]}"


def test_valid_provider_io_input_passes():
    """Check that valid provider-io input passes validation."""
    schema = load_schema("provider-io")
    repo_root = Path(__file__).parent.parent
    sample_path = repo_root / "tests" / "samples" / "valid" / "provider-io-input.json"
    data = load_sample(sample_path)

    validator = Draft202012Validator(schema)
    errors = list(validator.iter_errors(data))
    assert len(errors) == 0, f"Valid sample should pass: {[e.message for e in errors]}"


def test_valid_provider_io_output_passes():
    """Check that valid provider-io output passes validation."""
    schema = load_schema("provider-io")
    repo_root = Path(__file__).parent.parent
    sample_path = repo_root / "tests" / "samples" / "valid" / "provider-io-output.json"
    data = load_sample(sample_path)

    validator = Draft202012Validator(schema)
    errors = list(validator.iter_errors(data))
    assert len(errors) == 0, f"Valid sample should pass: {[e.message for e in errors]}"


def test_invalid_provider_io_error_missing_fails():
    """Check that provider-io output with error missing fails."""
    schema = load_schema("provider-io")
    repo_root = Path(__file__).parent.parent
    sample_path = repo_root / "tests" / "samples" / "invalid" / "provider-io-error-missing.json"
    data = load_sample(sample_path)

    validator = Draft202012Validator(schema)
    errors = list(validator.iter_errors(data))
    assert len(errors) > 0, "Invalid sample should fail validation"
    # Check for root error with oneOf validator and a context error with 'error' is a required property
    root_error = any(
        not e.absolute_path and e.validator == "oneOf"
        for e in errors
    )
    context_has_error_required = False
    for e in errors:
        if e.validator == "oneOf" and e.context:
            context_has_error_required = any(
                "'error' is a required property" in ctx.message
                for ctx in e.context
            )
    assert root_error and context_has_error_required, f"Expected oneOf error with 'error' required in context, got: {[(e.absolute_path, e.validator, e.message) for e in errors]}"


def test_valid_ticket_manifest_passes():
    """Check that valid ticket manifest passes validation."""
    schema = load_schema("ticket-manifest")
    repo_root = Path(__file__).parent.parent
    sample_path = repo_root / "tests" / "samples" / "valid" / "ticket-manifest.json"
    data = load_sample(sample_path)

    validator = Draft202012Validator(schema)
    errors = list(validator.iter_errors(data))
    assert len(errors) == 0, f"Valid sample should pass: {[e.message for e in errors]}"


def test_invalid_ticket_manifest_story_points_fails():
    """Check that manifest with story_points property fails (additionalProperties: false)."""
    schema = load_schema("ticket-manifest")
    repo_root = Path(__file__).parent.parent
    sample_path = repo_root / "tests" / "samples" / "invalid" / "ticket-manifest-story-points.json"
    data = load_sample(sample_path)

    validator = Draft202012Validator(schema)
    errors = list(validator.iter_errors(data))
    assert len(errors) > 0, "Invalid sample with story_points should fail validation"
    # Check that there's an error at epics.0.children.0 with message containing story_points
    error_at_path = any(
        ".".join(str(p) for p in e.absolute_path) == "epics.0.children.0" and
        "story_points" in e.message
        for e in errors
    )
    assert error_at_path, f"Expected error at epics.0.children.0 containing story_points, got: {[(e.absolute_path, e.message) for e in errors]}"


def test_valid_state_passes():
    """Check that valid state sample passes validation."""
    schema = load_schema("state")
    repo_root = Path(__file__).parent.parent
    sample_path = repo_root / "tests" / "samples" / "valid" / "state.json"
    data = load_sample(sample_path)

    validator = Draft202012Validator(schema)
    errors = list(validator.iter_errors(data))
    assert len(errors) == 0, f"Valid sample should pass: {[e.message for e in errors]}"


def test_invalid_state_bad_stage_fails():
    """Check that state with invalid stage fails."""
    schema = load_schema("state")
    repo_root = Path(__file__).parent.parent
    sample_path = repo_root / "tests" / "samples" / "invalid" / "state-bad-stage.json"
    data = load_sample(sample_path)

    validator = Draft202012Validator(schema)
    errors = list(validator.iter_errors(data))
    assert len(errors) > 0, "Invalid sample should fail validation"
    # Check that there's an error at stage with validator enum
    error_at_stage = any(
        ".".join(str(p) for p in e.absolute_path) == "stage" and
        e.validator == "enum"
        for e in errors
    )
    assert error_at_stage, f"Expected error at stage with validator enum, got: {[(e.absolute_path, e.validator, e.message) for e in errors]}"


def test_valid_pm_config_passes():
    """Check that valid pm-config sample passes validation."""
    schema = load_schema("pm-config")
    repo_root = Path(__file__).parent.parent
    sample_path = repo_root / "tests" / "samples" / "valid" / "pm-config.yaml"
    data = yaml.safe_load(open(sample_path))

    validator = Draft202012Validator(schema)
    errors = list(validator.iter_errors(data))
    assert len(errors) == 0, f"Valid sample should pass: {[e.message for e in errors]}"


def test_invalid_pm_config_bad_jira_mode_fails():
    """Check that pm-config with invalid jira.mode fails."""
    schema = load_schema("pm-config")
    repo_root = Path(__file__).parent.parent
    sample_path = repo_root / "tests" / "samples" / "invalid" / "pm-config-bad-jira-mode.yaml"
    data = yaml.safe_load(open(sample_path))

    validator = Draft202012Validator(schema)
    errors = list(validator.iter_errors(data))
    assert len(errors) > 0, "Invalid sample should fail validation"
    # Check that there's an error at jira.mode with validator enum
    error_at_jira_mode = any(
        ".".join(str(p) for p in e.absolute_path) == "jira.mode" and
        e.validator == "enum"
        for e in errors
    )
    assert error_at_jira_mode, f"Expected error at jira.mode with validator enum, got: {[(e.absolute_path, e.validator, e.message) for e in errors]}"


def test_valid_registry_passes():
    """Check that valid registry sample passes validation."""
    schema = load_schema("registry")
    repo_root = Path(__file__).parent.parent
    sample_path = repo_root / "tests" / "samples" / "valid" / "registry.yaml"
    data = yaml.safe_load(open(sample_path))

    validator = Draft202012Validator(schema)
    errors = list(validator.iter_errors(data))
    assert len(errors) == 0, f"Valid sample should pass: {[e.message for e in errors]}"


def test_invalid_registry_mcp_no_server_fails():
    """Check that registry with missing server in MCP provider fails."""
    schema = load_schema("registry")
    repo_root = Path(__file__).parent.parent
    sample_path = repo_root / "tests" / "samples" / "invalid" / "registry-mcp-no-server.yaml"
    data = yaml.safe_load(open(sample_path))

    validator = Draft202012Validator(schema)
    errors = list(validator.iter_errors(data))
    assert len(errors) > 0, "Invalid sample should fail validation"
    # Check that there's an error at providers.0 with message containing 'server' is a required property
    error_at_providers = any(
        ".".join(str(p) for p in e.absolute_path) == "providers.0" and
        "'server' is a required property" in e.message
        for e in errors
    )
    assert error_at_providers, f"Expected error at providers.0 containing 'server' required, got: {[(e.absolute_path, e.message) for e in errors]}"
