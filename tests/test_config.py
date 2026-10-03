"""Test configuration files."""

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


def load_config_yaml(file_name):
    """Load a YAML config file."""
    repo_root = Path(__file__).parent.parent
    file_path = repo_root / file_name
    with open(file_path) as f:
        return yaml.safe_load(f)


def test_pm_config_exists():
    """Check that pm.config.yaml exists and is readable."""
    repo_root = Path(__file__).parent.parent
    config_path = repo_root / "pm.config.yaml"
    assert config_path.exists(), "pm.config.yaml does not exist"


def test_pm_config_validates():
    """Check that pm.config.yaml validates against pm-config.schema.json."""
    schema = load_schema("pm-config")
    config = load_config_yaml("pm.config.yaml")

    validator = Draft202012Validator(schema)
    errors = list(validator.iter_errors(config))

    assert len(errors) == 0, f"pm.config.yaml validation errors: {[e.message for e in errors]}"


def test_pm_config_jira_mode_dry_run():
    """Check that pm.config.yaml has jira.mode: dry_run."""
    config = load_config_yaml("pm.config.yaml")
    assert config["jira"]["mode"] == "dry_run", "jira.mode should be dry_run"


def test_pm_config_has_placeholder_values():
    """Check that pm.config.yaml has only placeholder values (no real sites/keys)."""
    config = load_config_yaml("pm.config.yaml")

    # Check that key config values are placeholders
    assert "[[" in str(config["product"]["name"]), "product.name should be a placeholder"
    assert "[[" in str(config["product"]["vision"]), "product.vision should be a placeholder"
    assert "[[" in str(config["jira"]["site"]), "jira.site should be a placeholder"
    assert "[[" in str(config["jira"]["project_key"]), "jira.project_key should be a placeholder"


def test_registry_yaml_exists():
    """Check that connectors/registry.yaml exists and is readable."""
    repo_root = Path(__file__).parent.parent
    registry_path = repo_root / "connectors" / "registry.yaml"
    assert registry_path.exists(), "connectors/registry.yaml does not exist"


def test_registry_validates():
    """Check that connectors/registry.yaml validates against registry.schema.json."""
    schema = load_schema("registry")
    repo_root = Path(__file__).parent.parent
    registry_path = repo_root / "connectors" / "registry.yaml"
    with open(registry_path) as f:
        registry = yaml.safe_load(f)

    validator = Draft202012Validator(schema)
    errors = list(validator.iter_errors(registry))

    assert len(errors) == 0, f"registry.yaml validation errors: {[e.message for e in errors]}"


def test_no_provider_enabled_by_default():
    """Check that no provider is enabled in connectors/registry.yaml."""
    repo_root = Path(__file__).parent.parent
    registry_path = repo_root / "connectors" / "registry.yaml"
    with open(registry_path) as f:
        registry = yaml.safe_load(f)

    for provider in registry.get("providers", []):
        assert provider.get("enabled") is False, f"Provider {provider['id']} should not be enabled"


def test_pm_config_has_pii_tables():
    """Check that pm.config.yaml has data.pii_tables."""
    config = load_config_yaml("pm.config.yaml")
    assert "pii_tables" in config["data"], "data.pii_tables is missing"
    assert isinstance(config["data"]["pii_tables"], list), "data.pii_tables should be a list"


def test_pm_config_has_anecdotes_allow_company_names():
    """Check that pm.config.yaml has anecdotes.allow_company_names."""
    config = load_config_yaml("pm.config.yaml")
    assert "anecdotes" in config, "anecdotes section is missing"
    assert "allow_company_names" in config["anecdotes"], "anecdotes.allow_company_names is missing"
    assert config["anecdotes"]["allow_company_names"] is False, "allow_company_names should be false"
