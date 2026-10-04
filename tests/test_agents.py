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
    assert lines[1] == 'name: meeting-to-prd'
    assert lines[2].startswith('description: ') and 'Gate A' in lines[2]
    assert lines[3] == '---'

    # Check for required sections (executable steps format)
    assert "## Trigger" in content
    assert "## Setup" in content or "## Execution" in content
    assert ".venv/bin/python scripts/intake.py" in content
    assert "Validate" in content
    assert "state.json" in content


TIER_TO_MODEL = {"small": "haiku", "medium": "sonnet", "large": "opus"}
REPO = Path(__file__).parent.parent


def test_prd_auditor_exists_and_name():
    path = REPO / ".claude" / "agents" / "prd-auditor.md"
    assert path.exists(), "prd-auditor.md not found"
    fm = parse_agent_file(path)
    assert fm["name"] == "prd-auditor"
    assert fm["description"]


def test_prd_auditor_model_matches_config_tier():
    with open(REPO / "pm.config.yaml") as f:
        config = yaml.safe_load(f)
    fm = parse_agent_file(REPO / ".claude" / "agents" / "prd-auditor.md")
    expected = TIER_TO_MODEL[config["models"]["prd_auditor"]]
    assert fm["model"] == expected, f"prd-auditor model should be {expected}, got {fm['model']}"


def test_prd_auditor_tools_are_read_only():
    fm = parse_agent_file(REPO / ".claude" / "agents" / "prd-auditor.md")
    tools = [t.strip() for t in fm["tools"].split(",")]
    assert set(tools) == {"Read"}, f"prd-auditor tools should be exactly {{Read}}, got {set(tools)}"


def test_prd_auditor_forbids_problem_and_notes():
    body = (REPO / ".claude" / "agents" / "prd-auditor.md").read_text()
    assert "Do not read `02-problem.md`" in body
    assert "ONLY one JSON object" in body


def test_prd_writer_has_three_modes():
    body = (REPO / ".claude" / "agents" / "prd-writer.md").read_text()
    for heading in ("## Mode 1: problem framing", "## Mode 2: PRD draft", "## Mode 3: PRD revision"):
        assert heading in body


def test_pm_approve_disables_model_invocation():
    fm = parse_agent_file(REPO / ".claude" / "skills" / "pm-approve" / "SKILL.md")
    assert fm["name"] == "pm-approve"
    assert fm["disable-model-invocation"] is True


def test_prd_audit_skill_name():
    fm = parse_agent_file(REPO / ".claude" / "skills" / "prd-audit" / "SKILL.md")
    assert fm["name"] == "prd-audit"


def test_skill_files_under_200_lines():
    for skill in ("meeting-to-prd", "prd-audit", "pm-approve"):
        lines = (REPO / ".claude" / "skills" / skill / "SKILL.md").read_text().splitlines()
        assert len(lines) < 200, f"{skill} SKILL.md has {len(lines)} lines"


def test_meeting_to_prd_never_approves():
    body = (REPO / ".claude" / "skills" / "meeting-to-prd" / "SKILL.md").read_text()
    assert "must never run `scripts/approve.py`" in body
    assert "shasum -a 256" in body
    assert "audit.max_revision_loops" in body


# --- M3 + M4: data-enricher, anecdote-curator, new skills, settings ---
def _tier_model(key):
    with open(REPO / "pm.config.yaml") as f:
        config = yaml.safe_load(f)
    return TIER_TO_MODEL[config["models"][key]]


def test_data_enricher_front_matter_and_tier():
    fm = parse_agent_file(REPO / ".claude" / "agents" / "data-enricher.md")
    assert fm["name"] == "data-enricher"
    assert fm["description"]
    assert fm["model"] == _tier_model("enrichment")
    assert {t.strip() for t in fm["tools"].split(",")} == {"Read", "Bash"}


def test_data_enricher_never_writes_cards():
    body = (REPO / ".claude" / "agents" / "data-enricher.md").read_text()
    assert "NEVER write or edit files under `03-evidence/`" in body
    assert "scripts/enrich.py run" in body
    assert "scripts/validate_evidence.py" in body


def test_anecdote_curator_front_matter_and_tier():
    fm = parse_agent_file(REPO / ".claude" / "agents" / "anecdote-curator.md")
    assert fm["name"] == "anecdote-curator"
    assert fm["description"]
    assert fm["model"] == _tier_model("anecdotes")
    assert {t.strip() for t in fm["tools"].split(",")} == {"Read", "Write"}


def test_anecdote_curator_copies_records_exactly():
    body = (REPO / ".claude" / "agents" / "anecdote-curator.md").read_text()
    assert "EXACTLY" in body
    assert "counter-anecdote" in body
    assert "frequency_hint" in body


def test_new_skills_exist_with_matching_name():
    for skill in ("data-enrichment", "customer-anecdotes"):
        path = REPO / ".claude" / "skills" / skill / "SKILL.md"
        assert path.exists(), f"{skill} SKILL.md not found"
        fm = parse_agent_file(path)
        assert fm["name"] == skill
        assert fm["description"]


def test_every_skill_file_under_200_lines():
    skill_files = list((REPO / ".claude" / "skills").glob("*/SKILL.md"))
    assert len(skill_files) >= 5
    for path in skill_files:
        lines = path.read_text().splitlines()
        assert len(lines) < 200, f"{path.parent.name} SKILL.md has {len(lines)} lines"


def test_meeting_to_prd_evidence_step_runs_both_in_parallel():
    body = (REPO / ".claude" / "skills" / "meeting-to-prd" / "SKILL.md").read_text()
    assert "data-enrichment" in body and "customer-anecdotes" in body
    assert "in parallel" in body
    assert "No data provider configured" in body


def test_settings_json_is_valid_and_references_four_hooks():
    import json

    raw = (REPO / ".claude" / "settings.json").read_text()
    settings = json.loads(raw)
    assert "hooks" in settings
    for script in ("guard_approvals.py", "validate_artifact.py", "guard_readonly_query.py", "pii_scan.py"):
        assert script in raw, f"{script} not referenced in settings.json"
        assert (REPO / ".claude" / "hooks" / script).exists(), f"{script} missing"
    pre_matchers = {entry["matcher"] for entry in settings["hooks"]["PreToolUse"]}
    assert {"Write|Edit", "Bash", "mcp__.*"} <= pre_matchers


# --- M5: ux-designer, ux-auditor, new skills ---
def test_ux_designer_front_matter_and_tier():
    fm = parse_agent_file(REPO / ".claude" / "agents" / "ux-designer.md")
    assert fm["name"] == "ux-designer"
    assert fm["description"]
    assert fm["model"] == _tier_model("ux_designer") == "sonnet"
    assert {t.strip() for t in fm["tools"].split(",")} == {"Read", "Write", "Edit", "Bash"}


def test_ux_designer_has_two_modes_and_runs_validator():
    body = (REPO / ".claude" / "agents" / "ux-designer.md").read_text()
    for heading in ("## Mode 1: design", "## Mode 2: revision"):
        assert heading in body
    assert "scripts/validate_ux.py" in body
    assert "lorem ipsum" in body
    assert "Never touch `prd.md`" in body


def test_ux_auditor_front_matter_and_tier():
    fm = parse_agent_file(REPO / ".claude" / "agents" / "ux-auditor.md")
    assert fm["name"] == "ux-auditor"
    assert fm["description"]
    assert fm["model"] == _tier_model("ux_auditor") == "sonnet"
    tools = {t.strip() for t in fm["tools"].split(",")}
    assert tools == {"Read"}
    assert not tools & {"Write", "Edit", "Bash"}


def test_ux_auditor_returns_json_only_and_no_verdict():
    body = (REPO / ".claude" / "agents" / "ux-auditor.md").read_text()
    assert "ONLY one JSON object" in body
    assert "schemas/ux-audit.schema.json" in body
    assert "Do not compute or state the verdict" in body


def test_ux_skills_exist_with_matching_name_and_size():
    for skill in ("prd-to-ux", "ux-audit"):
        path = REPO / ".claude" / "skills" / skill / "SKILL.md"
        assert path.exists(), f"{skill} SKILL.md not found"
        fm = parse_agent_file(path)
        assert fm["name"] == skill
        assert fm["description"]
        assert len(path.read_text().splitlines()) < 200


def test_prd_to_ux_skill_never_approves_and_loops():
    body = (REPO / ".claude" / "skills" / "prd-to-ux" / "SKILL.md").read_text()
    assert "/pm-ux <run-id>" in body
    assert "scripts/check_approval.py runs/<run-id> prd" in body
    assert "scripts/render_ux_audit.py" in body
    assert "audit.max_revision_loops" in body
    assert "must never run `scripts/approve.py`" in body
    assert "/pm-approve ux <run-id>" in body


def test_pm_approve_covers_ux_and_stays_human_only():
    path = REPO / ".claude" / "skills" / "pm-approve" / "SKILL.md"
    fm = parse_agent_file(path)
    assert fm["disable-model-invocation"] is True
    body = path.read_text()
    assert "/pm-approve ux <run-id>" in body
    assert "traceability.md" in body


# --- M6: ticket-architect, prd-to-tickets skill, pm-approve Gate C ---
def test_ticket_architect_front_matter_and_tier():
    fm = parse_agent_file(REPO / ".claude" / "agents" / "ticket-architect.md")
    assert fm["name"] == "ticket-architect"
    assert fm["description"]
    assert fm["model"] == _tier_model("ticket_architect") == "sonnet"
    assert {t.strip() for t in fm["tools"].split(",")} == {"Read", "Write", "Bash"}


def test_ticket_architect_rules_and_scripts():
    body = (REPO / ".claude" / "agents" / "ticket-architect.md").read_text()
    for heading in ("## Mode 1: design", "## Mode 2: revision"):
        assert heading in body
    assert "scripts/validate_tickets.py" in body
    assert "scripts/preview_tickets.py" in body
    assert "Never Sub-tasks" in body
    assert "Never add story points" in body
    assert "`jira_key` is always `null`" in body
    assert "never run `scripts/approve.py` or `scripts/jira_publish.py`" in body
    assert "Never touch `prd.md`" in body


def test_prd_to_tickets_skill_exists_and_stays_human_gated():
    path = REPO / ".claude" / "skills" / "prd-to-tickets" / "SKILL.md"
    assert path.exists(), "prd-to-tickets SKILL.md not found"
    fm = parse_agent_file(path)
    assert fm["name"] == "prd-to-tickets"
    assert fm["description"]
    body = path.read_text()
    assert len(body.splitlines()) < 200
    assert "/pm-tickets <run-id>" in body
    assert "scripts/check_approval.py runs/<run-id> ux" in body
    assert "scripts/validate_tickets.py" in body
    assert "audit.max_revision_loops" in body
    assert "scripts/jira_publish.py" in body
    assert "Nothing is sent to Jira" in body
    assert "must never run `scripts/approve.py`" in body
    assert "/pm-approve tickets <run-id>" in body


def test_pm_approve_covers_tickets_and_stays_human_only():
    path = REPO / ".claude" / "skills" / "pm-approve" / "SKILL.md"
    fm = parse_agent_file(path)
    assert fm["disable-model-invocation"] is True
    body = path.read_text()
    assert "/pm-approve tickets <run-id>" in body
    assert "No override exists for tickets" in body
    assert "Writing Jira keys" in body
