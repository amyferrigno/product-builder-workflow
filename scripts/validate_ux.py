#!/usr/bin/env python3
"""
Validate the UX folder (runs/<id>/ux/) against the UX contract.
Usage: python scripts/validate_ux.py <run_dir> [--spec-only]

Checks flows.md, spec.md, index.html and screens/*.html: required states, REQ
traceability, Must coverage, self-contained HTML, design tokens, accessibility
basics. --spec-only checks only spec.md format and REQ ids.
One error per line; exit 0 when clean, 1 otherwise. Never a traceback.
"""

import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit_verdict import prd_has_ai_addendum  # noqa: E402
from validate_prd import parse_requirements, remove_html_comments  # noqa: E402

try:
    import yaml
except ImportError as e:
    print(f"Error: Missing required module: {e}", file=sys.stderr)
    sys.exit(2)

REQUIRED_STATES = ["default", "loading", "empty", "error", "success"]
AI_STATES = ["low-confidence", "user-edit", "regenerate", "explanation", "escalation"]
SPEC_SUBHEADINGS = ["Components", "Copy", "Interactions", "Analytics events"]

SCREEN_FILE_RE = re.compile(r'^SCR-(\d{3})-[a-z0-9]+(?:-[a-z0-9]+)*\.html$')
REQ_ID_RE = re.compile(r'^REQ-\d{3}$')
COLOUR_RE = re.compile(r'(?<![\w/])#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(', re.IGNORECASE)
ANCHOR_HREF_RE = re.compile(r'\bhref\s*=\s*(?:"#[^"]*"|\'#[^\']*\')', re.IGNORECASE)
URL_RE = re.compile(r'https?://|(?:^|[\s"\'(=,])//[\w-]+\.[\w-]+', re.IGNORECASE)
HIDDEN_TAGS = {"script", "style", "template"}
VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
    "meta", "param", "source", "track", "wbr",
}


# --- configuration ---------------------------------------------------------

def default_repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def resolve_tokens_path(repo_root: Path, config_path: Optional[Path] = None) -> Path:
    """Tokens file from ux.design_tokens; the default template for a placeholder or missing value."""
    default = repo_root / "templates" / "ux-tokens.css"
    config = Path(config_path) if config_path else repo_root / "pm.config.yaml"
    try:
        data = yaml.safe_load(config.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return default
    ux = data.get("ux") if isinstance(data, dict) else None
    value = ux.get("design_tokens") if isinstance(ux, dict) else None
    if not isinstance(value, str) or not value.strip() or re.search(r'\[\[.*\]\]', value):
        return default
    path = Path(value.strip())
    return path if path.is_absolute() else repo_root / path


# --- markdown parsing ------------------------------------------------------

def split_sections(text: str, heading_re: "re.Pattern[str]") -> List[Tuple[str, str, str]]:
    """Split markdown on '## ' headings matching heading_re (groups: id, title).

    Returns (id, title, body) in order. Other '## ' headings end a section.
    """
    sections: List[Tuple[str, str, str]] = []
    current: Optional[Tuple[str, str]] = None
    body: List[str] = []
    for line in remove_html_comments(text).split('\n'):
        if line.startswith('## '):
            if current:
                sections.append((current[0], current[1], '\n'.join(body)))
            match = heading_re.match(line)
            current = (match.group(1), match.group(2).strip()) if match else None
            body = []
        elif current:
            body.append(line)
    if current:
        sections.append((current[0], current[1], '\n'.join(body)))
    return sections


SPEC_HEADING_RE = re.compile(r'^##\s+(SCR-\d{3})\s+(.+)$')
FLOW_HEADING_RE = re.compile(r'^##\s+(FLOW-\d{3})\s+(.+)$')


def parse_reqs_line(body: str) -> Optional[List[str]]:
    """Tokens of the '**REQs**: a, b' line, or None when the line is absent."""
    match = re.search(r'^\*\*REQs\*\*:[ \t]*(.*)$', body, re.MULTILINE)
    if not match:
        return None
    return [t.strip() for t in match.group(1).split(',') if t.strip()]


def spec_screen_reqs(spec_text: str) -> Dict[str, List[str]]:
    """Map SCR id to the REQ ids listed under its '**REQs**' line."""
    result: Dict[str, List[str]] = {}
    for scr_id, _title, body in split_sections(spec_text, SPEC_HEADING_RE):
        result[scr_id] = [t for t in (parse_reqs_line(body) or []) if REQ_ID_RE.match(t)]
    return result


def check_reqs_line(where: str, body: str, prd_reqs: Set[str]) -> List[str]:
    errors: List[str] = []
    tokens = parse_reqs_line(body)
    if tokens is None:
        return [f"{where}: missing **REQs** line"]
    if not tokens:
        errors.append(f"{where}: **REQs** line is empty")
    for token in tokens:
        if not REQ_ID_RE.match(token):
            errors.append(f"{where}: malformed requirement id '{token}'")
        elif token not in prd_reqs:
            errors.append(f"{where}: unknown requirement {token} (not in prd.md)")
    return errors


def check_spec(spec_text: str, prd_reqs: Set[str]) -> List[str]:
    errors: List[str] = []
    seen: Set[str] = set()
    for scr_id, _title, body in split_sections(spec_text, SPEC_HEADING_RE):
        where = f"spec.md {scr_id}"
        if scr_id in seen:
            errors.append(f"{where}: duplicate section")
        seen.add(scr_id)
        purpose = re.search(r'^\*\*Purpose\*\*:[ \t]*(.*)$', body, re.MULTILINE)
        if not purpose or not purpose.group(1).strip():
            errors.append(f"{where}: missing or empty **Purpose**")
        errors.extend(check_reqs_line(where, body, prd_reqs))
        parts = re.split(r'^###\s+(.+?)\s*$', body, flags=re.MULTILINE)
        subs = {parts[i].strip(): parts[i + 1].strip() for i in range(1, len(parts) - 1, 2)}
        for name in SPEC_SUBHEADINGS:
            if name not in subs:
                errors.append(f"{where}: missing sub-heading '### {name}'")
            elif not subs[name]:
                errors.append(f"{where}: sub-heading '### {name}' is empty")
    if not seen:
        errors.append("spec.md: no '## SCR-### <Name>' sections found")
    return errors


def check_flows(flows_text: str, prd_reqs: Set[str]) -> List[str]:
    errors: List[str] = []
    sections = split_sections(flows_text, FLOW_HEADING_RE)
    if not sections:
        return ["flows.md: no '## FLOW-### <Title>' sections found"]
    for flow_id, _title, body in sections:
        where = f"flows.md {flow_id}"
        errors.extend(check_reqs_line(where, body, prd_reqs))
        blocks = re.findall(r'^```mermaid[ \t]*\n.*?^```', body, re.MULTILINE | re.DOTALL)
        if len(blocks) != 1:
            errors.append(f"{where}: expected exactly one mermaid block, found {len(blocks)}")
        elif not re.sub(r'^```mermaid|```$', '', blocks[0], flags=re.MULTILINE).strip():
            errors.append(f"{where}: mermaid block is empty")
    return errors


# --- HTML parsing ----------------------------------------------------------

class ScreenParser(HTMLParser):
    """Collects the facts the validator needs from one screen or index page."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.lang = ""
        self.title = ""
        self.mains: List[str] = []
        self.states: List[Dict[str, str]] = []
        self.styles: List[str] = []
        self.hrefs: List[str] = []
        self.external: List[str] = []
        self.urls: List[str] = []
        self.label_for: Set[str] = set()
        self.controls: List[Tuple[str, str, str]] = []
        self.images_without_alt = 0
        self.textless: List[str] = []
        self.stack: List[Dict] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        a = {k: (v or "") for k, v in attrs}
        item: Optional[Dict] = None
        if tag == "html":
            self.lang = a.get("lang", "").strip()
        elif tag == "main":
            self.mains.append(a.get("data-screen", ""))
        elif tag == "label" and a.get("for"):
            self.label_for.add(a["for"])
        elif tag == "img" and "alt" not in a:
            self.images_without_alt += 1
        elif tag in ("input", "select", "textarea") and a.get("type", "").lower() != "hidden":
            self.controls.append((tag, a.get("id", ""), a.get("aria-label", "").strip()))
        for attr in ("src", "href"):
            value = a.get(attr, "").strip()
            if attr == "href":
                self.hrefs.append(value)
            if value.lower().startswith(("http://", "https://", "//")):
                self.external.append(f"<{tag} {attr}=\"{value}\">")
        for attr, raw in a.items():
            if attr.lower().startswith("xmlns"):
                continue
            if attr in ("src", "href") and raw.strip().lower().startswith(("http://", "https://", "//")):
                continue
            if URL_RE.search(raw):
                self.urls.append(f"<{tag} {attr}>")
        if tag == "script" and "src" in a and not a["src"].lower().startswith(("http://", "https://", "//")):
            self.external.append("<script src>")
        if tag == "link" and "stylesheet" in a.get("rel", "").lower():
            self.external.append("<link rel=\"stylesheet\">")
        if tag in ("title", "style", "button", "a", "script"):
            item = {"kind": tag, "text": "", "aria": a.get("aria-label", "").strip()}
        elif tag == "section" and a.get("data-state") is not None and any(
            e["tag"] == "main" for e in self.stack
        ):
            item = {"kind": "state", "text": "", "id": a.get("id", ""), "name": a["data-state"]}
        if tag not in VOID_TAGS:
            self.stack.append({"tag": tag, "item": item})

    def handle_startendtag(self, tag: str, attrs) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag in VOID_TAGS or not any(e["tag"] == tag for e in self.stack):
            return
        while self.stack:
            entry = self.stack.pop()
            if entry["item"]:
                self._finish(entry["item"])
            if entry["tag"] == tag:
                break

    def _finish(self, item: Dict) -> None:
        kind = item["kind"]
        text = item["text"].strip()
        if kind == "title":
            self.title = text
        elif kind == "style":
            self.styles.append(item["text"])
            if URL_RE.search(item["text"]):
                self.urls.append("<style> content")
        elif kind == "script":
            if URL_RE.search(item["text"]):
                self.urls.append("inline <script> content")
        elif kind == "state":
            self.states.append({"id": item["id"], "name": item["name"], "text": text})
        elif not text and not item["aria"]:
            self.textless.append(kind)

    def handle_data(self, data: str) -> None:
        hidden = any(e["tag"] in HIDDEN_TAGS for e in self.stack)
        for entry in self.stack:
            item = entry["item"]
            if item and not (hidden and item["kind"] == "state"):
                item["text"] += data

    def close(self) -> None:
        super().close()
        while self.stack:
            entry = self.stack.pop()
            if entry["item"]:
                self._finish(entry["item"])


def parse_html(text: str) -> ScreenParser:
    parser = ScreenParser()
    parser.feed(text)
    parser.close()
    return parser


def check_screen(
    name: str, text: str, scr_id: str, required: List[str], tokens: str
) -> Tuple[List[str], List[str]]:
    """Return (errors, state names present) for one screen file."""
    where = f"screens/{name}"
    errors: List[str] = []
    p = parse_html(text)

    if not p.lang:
        errors.append(f"{where}: <html> needs a lang attribute")
    if not p.title:
        errors.append(f"{where}: missing or empty <title>")
    if len(p.mains) != 1:
        errors.append(f"{where}: expected exactly one <main data-screen>, found {len(p.mains)}")
    elif p.mains[0] != scr_id:
        errors.append(f"{where}: data-screen '{p.mains[0]}' does not match filename ({scr_id})")

    present: List[str] = []
    for state in p.states:
        present.append(state["name"])
        if state["id"] != f"state-{state['name']}":
            errors.append(f"{where}: state '{state['name']}' must have id 'state-{state['name']}'")
        if not state["text"]:
            errors.append(f"{where}: state '{state['name']}' is empty")
    for state_name in required:
        if state_name not in present:
            errors.append(f"{where}: missing state '{state_name}'")

    for ref in p.external:
        errors.append(f"{where}: external resource not allowed: {ref}")
    for ref in p.urls:
        errors.append(f"{where}: external URL not allowed in {ref}")

    tokens_ok = bool(p.styles) and p.styles[0].strip().startswith(tokens.strip())
    if not tokens_ok:
        errors.append(f"{where}: first <style> block must start with the exact design tokens")
    outside = text
    if tokens_ok:
        outside = text.replace(tokens.strip(), "", 1)
    outside = ANCHOR_HREF_RE.sub('href=""', outside)
    if COLOUR_RE.search(outside):
        errors.append(f"{where}: colour literal outside the tokens block (use var(--...))")

    if p.images_without_alt:
        errors.append(f"{where}: {p.images_without_alt} <img> without alt")
    for tag, control_id, aria in p.controls:
        if not aria and not (control_id and control_id in p.label_for):
            errors.append(f"{where}: <{tag}> without a label (aria-label or <label for>)")
    for kind in p.textless:
        if kind in ("button", "a"):
            errors.append(f"{where}: <{kind}> without text or aria-label")
    return errors, present


# --- main validation -------------------------------------------------------

def validate_ux(
    run_dir, repo_root=None, spec_only: bool = False, config_path=None
) -> List[str]:
    """Return a list of error strings for runs/<id>/ux (empty list means valid)."""
    run = Path(run_dir)
    root = Path(repo_root) if repo_root else default_repo_root()
    ux_dir = run / "ux"
    if not ux_dir.is_dir():
        return [f"ux folder not found: {ux_dir}"]
    try:
        prd_text = (run / "prd.md").read_text(encoding="utf-8")
    except OSError:
        return [f"prd.md not found in {run}"]

    requirements = parse_requirements(prd_text)
    prd_reqs = {r for r, _ in requirements}
    errors: List[str] = []

    spec_path = ux_dir / "spec.md"
    try:
        spec_text = spec_path.read_text(encoding="utf-8")
    except OSError:
        spec_text = None
        errors.append("spec.md: file not found")
    if spec_text is not None:
        errors.extend(check_spec(spec_text, prd_reqs))
    if spec_only:
        return errors

    try:
        flows_text = (ux_dir / "flows.md").read_text(encoding="utf-8")
        errors.extend(check_flows(flows_text, prd_reqs))
    except OSError:
        errors.append("flows.md: file not found")

    required = REQUIRED_STATES + (AI_STATES if prd_has_ai_addendum(prd_text) else [])
    tokens_path = resolve_tokens_path(root, config_path)
    try:
        tokens = tokens_path.read_text(encoding="utf-8")
    except OSError:
        return errors + [f"design tokens file not found: {tokens_path}"]

    screens_dir = ux_dir / "screens"
    screen_files = sorted(screens_dir.glob("*.html")) if screens_dir.is_dir() else []
    screen_states: Dict[str, List[str]] = {}
    screen_names: Dict[str, str] = {}
    numbers: List[int] = []
    for path in screen_files:
        match = SCREEN_FILE_RE.match(path.name)
        if not match:
            errors.append(f"screens/{path.name}: name must look like SCR-001-kebab-name.html")
            continue
        scr_id = f"SCR-{match.group(1)}"
        numbers.append(int(match.group(1)))
        screen_names[scr_id] = path.name
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            errors.append(f"screens/{path.name}: cannot read file")
            continue
        screen_errors, present = check_screen(path.name, text, scr_id, required, tokens)
        errors.extend(screen_errors)
        screen_states[scr_id] = present
    if not screen_files:
        errors.append("screens/: no screen files found")
    for i, number in enumerate(sorted(numbers), start=1):
        if number != i:
            errors.append(f"screens/: ids must run SCR-001.. with no gaps; expected SCR-{i:03d}, found SCR-{number:03d}")
            break

    errors.extend(check_index(ux_dir, screen_names, screen_states, required))

    if spec_text is not None:
        spec_ids = [s for s, _t, _b in split_sections(spec_text, SPEC_HEADING_RE)]
        for scr_id in screen_names:
            if scr_id not in spec_ids:
                errors.append(f"spec.md: no section for screen {scr_id}")
        for scr_id in spec_ids:
            if scr_id not in screen_names:
                errors.append(f"spec.md: section {scr_id} has no matching screen file")
        covered = {r for reqs in spec_screen_reqs(spec_text).values() for r in reqs}
        for req_id, priority in requirements:
            if priority == "Must" and req_id not in covered:
                errors.append(f"Must requirement {req_id} is not covered by any screen in spec.md")
    return errors


def check_index(
    ux_dir: Path, screen_names: Dict[str, str], screen_states: Dict[str, List[str]], required: List[str]
) -> List[str]:
    try:
        text = (ux_dir / "index.html").read_text(encoding="utf-8")
    except OSError:
        return ["index.html: file not found"]
    parsed = parse_html(text)
    links = set(parsed.hrefs)
    errors: List[str] = [f"index.html: external URL not allowed in {ref}" for ref in parsed.urls]
    for scr_id, filename in screen_names.items():
        target = f"screens/{filename}"
        if target not in links and not any(link.startswith(target + "#") for link in links):
            errors.append(f"index.html: missing link to screen {scr_id} ({target})")
        states = list(required) + [s for s in screen_states.get(scr_id, []) if s not in required]
        for state in states:
            if f"{target}#state-{state}" not in links:
                errors.append(f"index.html: missing link to state '{state}' of {scr_id}")
    return errors


def main() -> None:
    args = sys.argv[1:]
    spec_only = "--spec-only" in args
    args = [a for a in args if a != "--spec-only"]
    if len(args) != 1:
        print("Usage: python scripts/validate_ux.py <run_dir> [--spec-only]")
        sys.exit(1)
    try:
        errors = validate_ux(args[0], spec_only=spec_only)
    except (OSError, ValueError, UnicodeDecodeError) as e:
        print(str(e))
        sys.exit(1)
    for error in errors:
        print(error)
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
