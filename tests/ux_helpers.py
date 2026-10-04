"""Helpers to build a minimal valid UX run in a temp folder.

Usage in a test:
    from ux_helpers import make_ux_run
    run = make_ux_run(tmp_path, ai=True, screens=2)

The run holds a copy of a golden PRD (AI or non-AI) and a ux/ folder that
passes validate_ux with zero errors. Tests break it by editing one file.
"""

import sys
from pathlib import Path
from typing import List

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from validate_prd import parse_requirements

TOKENS = (REPO_ROOT / "templates" / "ux-tokens.css").read_text(encoding="utf-8").strip()
BASE_STATES = ["default", "loading", "empty", "error", "success"]
AI_STATES = ["low-confidence", "user-edit", "regenerate", "explanation", "escalation"]
NAMES = ["home", "details", "review", "settings", "help", "summary"]


def screen_html(scr_id: str, title: str, states: List[str]) -> str:
    sections = "\n".join(
        f'  <section id="state-{s}" data-state="{s}"><p>{title}: {s} state.</p></section>'
        for s in states
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{scr_id} {title}</title>
<style>
{TOKENS}
body {{ font-family: var(--font-family); color: var(--color-text); }}
</style>
</head>
<body>
<main data-screen="{scr_id}">
{sections}
</main>
</body>
</html>
"""


def make_ux_run(tmp_path: Path, ai: bool = False, screens: int = 2) -> Path:
    """Build tmp_path/run with prd.md and a valid ux/ folder; return the run dir.

    Screen 1 lists every requirement, so every Must is covered.
    """
    fixture = "ai-clear-fit" if ai else "clean-meeting"
    prd_text = (REPO_ROOT / "fixtures" / fixture / "golden" / "prd.md").read_text(encoding="utf-8")
    run = tmp_path / "run"
    (run / "ux" / "screens").mkdir(parents=True)
    (run / "prd.md").write_text(prd_text, encoding="utf-8")

    req_ids = [r for r, _ in parse_requirements(prd_text)]
    states = BASE_STATES + (AI_STATES if ai else [])
    files = []
    spec = ["# Screen spec", ""]
    for n in range(1, screens + 1):
        scr_id = f"SCR-{n:03d}"
        title = NAMES[(n - 1) % len(NAMES)].capitalize()
        filename = f"{scr_id}-{NAMES[(n - 1) % len(NAMES)]}.html"
        files.append(filename)
        (run / "ux" / "screens" / filename).write_text(screen_html(scr_id, title, states), encoding="utf-8")
        reqs = req_ids if n == 1 else req_ids[:1]
        spec += [
            f"## {scr_id} {title}",
            "",
            f"**Purpose**: Let the user work with {title.lower()}.",
            f"**REQs**: {', '.join(reqs)}",
            "",
            "### Components", "- A heading and a status area.", "",
            "### Copy", "- Short plain messages for each state.", "",
            "### Interactions", "- Links move between states.", "",
            "### Analytics events", "- screen_viewed", "",
        ]
    (run / "ux" / "spec.md").write_text("\n".join(spec), encoding="utf-8")

    flows = (
        "# Flows\n\n## FLOW-001 Main flow\n\n"
        f"**REQs**: {', '.join(req_ids)}\n\n"
        "```mermaid\nflowchart LR\n  A[SCR-001] --> B[SCR-002]\n```\n"
    )
    (run / "ux" / "flows.md").write_text(flows, encoding="utf-8")

    links = []
    for filename in files:
        links.append(f'<li><a href="screens/{filename}">{filename}</a></li>')
        for s in states:
            links.append(f'<li><a href="screens/{filename}#state-{s}">{filename} {s}</a></li>')
    index = (
        '<!DOCTYPE html>\n<html lang="en">\n<head><meta charset="utf-8"><title>Gallery</title></head>\n'
        "<body><main><ul>\n" + "\n".join(links) + "\n</ul></main></body>\n</html>\n"
    )
    (run / "ux" / "index.html").write_text(index, encoding="utf-8")
    return run
