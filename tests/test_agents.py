"""Test agent file structure and compliance."""

from pathlib import Path

import yaml


def parse_agent_file(path: Path) -> dict:
    """Parse an agent markdown file and extract front matter."""
    content = path.read_text()

    if not content.startswith('---'):
        raise ValueError(f"{path.name}: must start with ---")

    lines = content.split('\n')
    end_idx = None
    for i in range(1, len(lines)):
        if lines[i] == '---':
            end_idx = i
            break

    if end_idx is None:
        raise ValueError(f"{path.name}: missing closing ---")

    front_matter_text = '\n'.join(lines[1:end_idx])
    return yaml.safe_load(front_matter_text)


def test_notes_extractor_exists():
    """Test that notes-extractor.md exists."""
    path = Path(__file__).parent.parent / ".claude" / "agents" / "notes-extractor.md"
    assert path.exists(), "notes-extractor.md not found"


def test_notes_extractor_front_matter():
    """Test notes-extractor front matter."""
    path = Path(__file__).parent.parent / ".claude" / "agents" / "notes-extractor.md"
    fm = parse_agent_file(path)

    assert fm["name"] == "notes-extractor"
    assert "Extract" in fm["description"]
    assert fm["model"] == "haiku"
    tools = [t.strip() for t in fm["tools"].split(",")]
    assert "Read" in tools
    assert "Write" in tools
    assert "Edit" not in tools
    assert "Bash" not in tools


def test_prd_writer_exists():
    """Test that prd-writer.md exists."""
    path = Path(__file__).parent.parent / ".claude" / "agents" / "prd-writer.md"
    assert path.exists(), "prd-writer.md not found"


def test_prd_writer_front_matter():
    """Test prd-writer front matter."""
    path = Path(__file__).parent.parent / ".claude" / "agents" / "prd-writer.md"
    fm = parse_agent_file(path)

    assert fm["name"] == "prd-writer"
    assert "problem" in fm["description"].lower()
    assert fm["model"] == "opus"
    tools = [t.strip() for t in fm["tools"].split(",")]
    assert "Read" in tools
    assert "Write" in tools
    assert "Edit" in tools


def test_model_tiers_match_config():
    """Test that agent models match the tiers in pm.config.yaml."""
    import yaml as py_yaml

    config_path = Path(__file__).parent.parent / "pm.config.yaml"
    with open(config_path) as f:
        config = py_yaml.safe_load(f)

    # Mapping of tier names to model names
    tier_to_model = {
        "small": "haiku",
        "medium": "sonnet",
        "large": "opus"
    }

    # notes-extractor should be model: extraction
    path = Path(__file__).parent.parent / ".claude" / "agents" / "notes-extractor.md"
    fm = parse_agent_file(path)
    extraction_tier = config["models"]["extraction"]
    expected_model = tier_to_model[extraction_tier]
    assert fm["model"] == expected_model, \
        f"notes-extractor model should be {expected_model} (tier {extraction_tier}), got {fm['model']}"

    # prd-writer should be model: prd_writer
    path = Path(__file__).parent.parent / ".claude" / "agents" / "prd-writer.md"
    fm = parse_agent_file(path)
    prd_writer_tier = config["models"]["prd_writer"]
    expected_model = tier_to_model[prd_writer_tier]
    assert fm["model"] == expected_model, \
        f"prd-writer model should be {expected_model} (tier {prd_writer_tier}), got {fm['model']}"


def test_notes_extractor_tools_are_minimal():
    """Test that notes-extractor has minimal tool set (Read, Write only)."""
    path = Path(__file__).parent.parent / ".claude" / "agents" / "notes-extractor.md"
    fm = parse_agent_file(path)

    tools = [t.strip() for t in fm["tools"].split(",")]
    # Should only have Read and Write
    assert set(tools) == {"Read", "Write"}


def test_prd_writer_tools_are_least_privilege():
    """Test that prd-writer has least-privilege tool set (exactly Read, Write, Edit)."""
    path = Path(__file__).parent.parent / ".claude" / "agents" / "prd-writer.md"
    fm = parse_agent_file(path)

    tools = [t.strip() for t in fm["tools"].split(",")]
    # Should have exactly Read, Write, Edit
    assert set(tools) == {"Read", "Write", "Edit"}, \
        f"prd-writer tools should be exactly {{Read, Write, Edit}}, got {set(tools)}"


def test_skill_file_exists():
    """Test that skill file exists."""
    path = Path(__file__).parent.parent / ".claude" / "skills" / "meeting-to-prd" / "SKILL.md"
    assert path.exists(), "meeting-to-prd SKILL.md not found"


def test_skill_file_structure():
    """Test skill file has required sections."""
    path = Path(__file__).parent.parent / ".claude" / "skills" / "meeting-to-prd" / "SKILL.md"
    content = path.read_text()

    # Check for front matter
    assert content.startswith('---')
    lines = content.split('\n')
    assert lines[1:4] == ['name: meeting-to-prd', 'description: Turn meeting notes into a problem statement with an AI decision', '---']

    # Check for required sections (executable steps format)
    assert "## Trigger" in content
    assert "## Setup" in content or "## Execution" in content
    assert ".venv/bin/python scripts/intake.py" in content
    assert "Validate" in content
    assert "state.json" in content
