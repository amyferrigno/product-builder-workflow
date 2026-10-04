"""Test that all required folders and files exist."""

from pathlib import Path


def test_folders_exist():
    """Check that all required directories exist."""
    required_dirs = [
        ".claude/agents",
        ".claude/skills",
        ".claude/hooks",
        "connectors/queries",
        "connectors/providers",
        "templates",
        "schemas",
        "scripts",
        "fixtures",
        "tests",
        "runs",
    ]

    repo_root = Path(__file__).parent.parent
    for dir_path in required_dirs:
        full_path = repo_root / dir_path
        assert full_path.is_dir(), f"Directory {dir_path} does not exist"


def test_empty_folders_have_gitkeep():
    """Check that empty folders have .gitkeep."""
    empty_dirs = [
        ".claude/agents",
        ".claude/skills",
        ".claude/hooks",
        "connectors/queries",
        "connectors/providers",
        "templates",
        "fixtures",
        "runs",
    ]

    repo_root = Path(__file__).parent.parent
    for dir_path in empty_dirs:
        gitkeep_path = repo_root / dir_path / ".gitkeep"
        assert gitkeep_path.exists(), f"Missing .gitkeep in {dir_path}"


def test_config_files_exist():
    """Check that pm.config.yaml and connectors/registry.yaml exist."""
    repo_root = Path(__file__).parent.parent

    assert (repo_root / "pm.config.yaml").exists(), "Missing pm.config.yaml"
    assert (repo_root / "connectors" / "registry.yaml").exists(), "Missing connectors/registry.yaml"


def test_knowledge_files_exist():
    """Check that CLAUDE.md and README.md exist (decisions.md is a local log, not committed)."""
    repo_root = Path(__file__).parent.parent

    files = ["CLAUDE.md", "README.md"]
    for file_name in files:
        file_path = repo_root / file_name
        assert file_path.exists(), f"Missing {file_name}"


def test_schemas_exist():
    """Check that all required schema files exist."""
    required_schemas = [
        "pm-config.schema.json",
        "registry.schema.json",
        "extraction.schema.json",
        "evidence.schema.json",
        "anecdote.schema.json",
        "provider-io.schema.json",
        "ticket-manifest.schema.json",
        "state.schema.json",
    ]

    repo_root = Path(__file__).parent.parent
    schemas_dir = repo_root / "schemas"
    for schema_name in required_schemas:
        schema_path = schemas_dir / schema_name
        assert schema_path.exists(), f"Missing schema {schema_name}"


def test_validate_schema_script_exists():
    """Check that the validator script exists."""
    repo_root = Path(__file__).parent.parent
    script_path = repo_root / "scripts" / "validate_schema.py"
    assert script_path.exists(), "Missing scripts/validate_schema.py"


def test_claude_md_under_80_lines():
    """Check that CLAUDE.md is under 80 lines."""
    repo_root = Path(__file__).parent.parent
    claude_path = repo_root / "CLAUDE.md"

    with open(claude_path, 'r') as f:
        lines = f.readlines()

    assert len(lines) < 80, f"CLAUDE.md has {len(lines)} lines, should be under 80"
