"""Test scripts/validate_ux.py."""

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).parent))
from validate_ux import validate_ux
from ux_helpers import make_ux_run

REPO_ROOT = Path(__file__).parent.parent
SCREEN1 = "screens/SCR-001-home.html"


def edit(run, rel, old, new, count=-1):
    path = run / "ux" / rel
    text = path.read_text()
    assert old in text, f"{old!r} not in {rel}"
    path.write_text(text.replace(old, new, count))


def has(errors, *needles):
    return any(all(n in e for n in needles) for e in errors)


@pytest.mark.parametrize("ai", [False, True])
def test_valid_folder_passes(tmp_path, ai):
    run = make_ux_run(tmp_path, ai=ai, screens=2)
    assert validate_ux(run) == []


def test_valid_with_one_screen(tmp_path):
    run = make_ux_run(tmp_path, screens=1)
    assert validate_ux(run) == []


def test_missing_required_state(tmp_path):
    run = make_ux_run(tmp_path)
    edit(run, SCREEN1, '<section id="state-loading" data-state="loading"><p>Home: loading state.</p></section>', "")
    assert has(validate_ux(run), "missing state 'loading'")


def test_missing_ai_state_on_ai_prd(tmp_path):
    run = make_ux_run(tmp_path, ai=True)
    edit(run, SCREEN1, '<section id="state-escalation" data-state="escalation"><p>Home: escalation state.</p></section>', "")
    assert has(validate_ux(run), "missing state 'escalation'")


def test_ai_state_not_required_on_non_ai_prd(tmp_path):
    run = make_ux_run(tmp_path, ai=False)
    assert not has(validate_ux(run), "low-confidence")


def test_empty_state_section(tmp_path):
    run = make_ux_run(tmp_path)
    edit(run, SCREEN1, "<p>Home: error state.</p>", "")
    assert has(validate_ux(run), "state 'error' is empty")


def test_uncovered_must_requirement(tmp_path):
    run = make_ux_run(tmp_path)
    edit(run, "spec.md", "REQ-001, REQ-002, REQ-003", "REQ-001, REQ-003", 1)
    errors = validate_ux(run)
    assert has(errors, "Must requirement REQ-002")


def test_unknown_req_in_spec(tmp_path):
    run = make_ux_run(tmp_path)
    edit(run, "spec.md", "**REQs**: REQ-001\n", "**REQs**: REQ-001, REQ-999\n", 1)
    assert has(validate_ux(run), "spec.md", "REQ-999")


def test_unknown_req_in_flows(tmp_path):
    run = make_ux_run(tmp_path)
    edit(run, "flows.md", "**REQs**: REQ-001", "**REQs**: REQ-999, REQ-001", 1)
    assert has(validate_ux(run), "flows.md", "REQ-999")


def test_external_http_src(tmp_path):
    run = make_ux_run(tmp_path)
    edit(run, SCREEN1, "<main", '<img src="https://example.com/a.png" alt="x"><main', 1)
    assert has(validate_ux(run), "external resource")


def test_external_script_src(tmp_path):
    run = make_ux_run(tmp_path)
    edit(run, SCREEN1, "<main", '<script src="app.js"></script><main', 1)
    assert has(validate_ux(run), "external resource", "script")


def test_external_stylesheet_link(tmp_path):
    run = make_ux_run(tmp_path)
    edit(run, SCREEN1, "<style>", '<link rel="stylesheet" href="a.css"><style>', 1)
    assert has(validate_ux(run), "external resource", "stylesheet")


def test_colour_literal_outside_tokens(tmp_path):
    run = make_ux_run(tmp_path)
    edit(run, SCREEN1, "color: var(--color-text);", "color: #ff0000;", 1)
    assert has(validate_ux(run), "colour literal")


def test_rgb_literal_outside_tokens(tmp_path):
    run = make_ux_run(tmp_path)
    edit(run, SCREEN1, "color: var(--color-text);", "color: rgb(1, 2, 3);", 1)
    assert has(validate_ux(run), "colour literal")


def test_anchor_links_are_not_colour_literals(tmp_path):
    run = make_ux_run(tmp_path)
    edit(run, SCREEN1, "<main", '<a href="#bad">Back</a><main', 1)
    assert validate_ux(run) == []


def test_tokens_block_missing(tmp_path):
    run = make_ux_run(tmp_path)
    path = run / "ux" / SCREEN1
    text = path.read_text()
    start = text.index("<style>") + len("<style>")
    end = text.index("body {")
    path.write_text(text[:start] + "\n" + text[end:])
    assert has(validate_ux(run), "design tokens")


def test_tokens_block_altered(tmp_path):
    run = make_ux_run(tmp_path)
    edit(run, SCREEN1, "--space-1: 4px;", "--space-1: 5px;", 1)
    assert has(validate_ux(run), "design tokens")


def test_input_without_label(tmp_path):
    run = make_ux_run(tmp_path)
    edit(run, SCREEN1, "<main", '<input id="q" type="text"><main', 1)
    assert has(validate_ux(run), "<input> without a label")


def test_input_with_label_passes(tmp_path):
    run = make_ux_run(tmp_path)
    edit(run, SCREEN1, "<main", '<label for="q">Q</label><input id="q" type="text"><input aria-label="Z"><main', 1)
    assert validate_ux(run) == []


def test_img_without_alt(tmp_path):
    run = make_ux_run(tmp_path)
    edit(run, SCREEN1, "<main", '<img src="a.png"><main', 1)
    assert has(validate_ux(run), "<img> without alt")


def test_button_without_text(tmp_path):
    run = make_ux_run(tmp_path)
    edit(run, SCREEN1, "<main", "<button></button><main", 1)
    assert has(validate_ux(run), "<button> without text")


def test_screen_missing_from_index(tmp_path):
    run = make_ux_run(tmp_path)
    path = run / "ux" / "index.html"
    path.write_text("\n".join(l for l in path.read_text().split("\n") if "SCR-002" not in l))
    assert has(validate_ux(run), "index.html", "SCR-002")


def test_state_link_missing_from_index(tmp_path):
    run = make_ux_run(tmp_path)
    path = run / "ux" / "index.html"
    path.write_text("\n".join(l for l in path.read_text().split("\n") if "#state-empty" not in l or "SCR-001" not in l))
    assert has(validate_ux(run), "index.html", "state 'empty' of SCR-001")


def test_screen_missing_from_spec(tmp_path):
    run = make_ux_run(tmp_path)
    path = run / "ux" / "spec.md"
    text = path.read_text()
    path.write_text(text[:text.index("## SCR-002")])
    assert has(validate_ux(run), "no section for screen SCR-002")


def test_spec_section_without_screen(tmp_path):
    run = make_ux_run(tmp_path)
    path = run / "ux" / "spec.md"
    path.write_text(path.read_text() + (
        "\n## SCR-003 Extra\n\n**Purpose**: x\n**REQs**: REQ-001\n\n"
        "### Components\n- a\n\n### Copy\n- a\n\n### Interactions\n- a\n\n### Analytics events\n- a\n"
    ))
    assert has(validate_ux(run), "SCR-003", "no matching screen")


def test_missing_spec_subheading(tmp_path):
    run = make_ux_run(tmp_path)
    edit(run, "spec.md", "### Copy\n- Short plain messages for each state.\n\n", "", 1)
    assert has(validate_ux(run), "SCR-001", "missing sub-heading '### Copy'")


def test_gap_in_screen_numbering(tmp_path):
    run = make_ux_run(tmp_path, screens=3)
    (run / "ux" / "screens" / "SCR-002-details.html").unlink()
    assert has(validate_ux(run), "no gaps")


def test_data_screen_not_matching_filename(tmp_path):
    run = make_ux_run(tmp_path)
    edit(run, SCREEN1, 'data-screen="SCR-001"', 'data-screen="SCR-009"')
    assert has(validate_ux(run), "does not match filename")


def test_flows_without_mermaid_block(tmp_path):
    run = make_ux_run(tmp_path)
    edit(run, "flows.md", "```mermaid", "```text")
    assert has(validate_ux(run), "flows.md", "mermaid")


def test_missing_ux_folder(tmp_path):
    run = make_ux_run(tmp_path)
    import shutil
    shutil.rmtree(run / "ux")
    errors = validate_ux(run)
    assert len(errors) == 1 and "ux folder not found" in errors[0]


def test_spec_only_ignores_screen_problems(tmp_path):
    run = make_ux_run(tmp_path)
    (run / "ux" / "index.html").unlink()
    edit(run, SCREEN1, 'data-screen="SCR-001"', 'data-screen="SCR-009"')
    assert validate_ux(run, spec_only=True) == []


def test_spec_only_still_checks_req_ids(tmp_path):
    run = make_ux_run(tmp_path)
    edit(run, "spec.md", "REQ-001, REQ-002", "REQ-001, REQ-998", 1)
    assert has(validate_ux(run, spec_only=True), "REQ-998")


def test_config_tokens_file_is_used(tmp_path):
    run = make_ux_run(tmp_path)
    tokens = tmp_path / "other.css"
    tokens.write_text(":root { --x: 1px; }")
    config = tmp_path / "pm.config.yaml"
    config.write_text(f"ux:\n  design_tokens: {tokens}\n")
    # screens carry the default tokens, so a different configured file must fail
    assert has(validate_ux(run, config_path=config), "design tokens")


def test_placeholder_config_uses_default_tokens(tmp_path):
    run = make_ux_run(tmp_path)
    config = tmp_path / "pm.config.yaml"
    config.write_text('ux:\n  design_tokens: "[[PATH_TO_TOKENS_OR_DESIGN_SYSTEM]]"\n')
    assert validate_ux(run, config_path=config) == []


def test_cli_exit_codes(tmp_path):
    run = make_ux_run(tmp_path)
    script = str(REPO_ROOT / "scripts" / "validate_ux.py")
    ok = subprocess.run([sys.executable, script, str(run)], capture_output=True, text=True)
    assert ok.returncode == 0
    (run / "ux" / "flows.md").unlink()
    bad = subprocess.run([sys.executable, script, str(run)], capture_output=True, text=True)
    assert bad.returncode == 1 and "flows.md" in bad.stdout and "Traceback" not in bad.stderr
    missing = subprocess.run([sys.executable, script, str(tmp_path / "nope")], capture_output=True, text=True)
    assert missing.returncode == 1 and "Traceback" not in missing.stderr
