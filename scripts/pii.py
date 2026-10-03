#!/usr/bin/env python3
"""
PII scanner and scrubber.
Usage:
    python scripts/pii.py scan <file> [--config pm.config.yaml]
    python scripts/pii.py scrub <file> [--config pm.config.yaml]

scan prints one finding per line (<file>:<line>: <type>: <match>); exit 1 if any, 0 if clean.
scrub prints the scrubbed text.

The core scan/scrub functions use the standard library only. PyYAML is imported
lazily in load_pii_config, which falls back to a small tolerant reader when PyYAML
is not installed (so hooks can run on a bare interpreter).

Documented non-goals (kept out to avoid false positives):
  - addresses without a dot in the domain (x@localhost) are not detected as emails;
  - a bare run of digits shorter than 10 or longer than 11 is treated as a count or id,
    not a phone number;
  - numbers split across line breaks are not detected as phones.
"""

import os
import re
import sys

URL_USERINFO_RE = re.compile(r"[A-Za-z][A-Za-z0-9+.\-]*://[^\s/@]+@[^\s\"'<>)\]]+")
# \w is unicode-aware in Python 3, so letters and digits of any script are accepted.
EMAIL_RE = re.compile(r"[\w.%+\-]+@[\w\-]+(?:\.[\w\-]+)+")
# Dash-like characters: hyphen-minus, U+2010 to U+2015 (hyphen, non-breaking hyphen, figure,
# en and em dashes, horizontal bar) and U+2212 (minus sign).
DASHES = "\\-\u2010-\u2015\u2212"
# Candidate phone: digits with single-line separators (space, dot, dash, parentheses).
PHONE_RE = re.compile(r"(?<![\w" + DASHES + r"])(?<!\d\.)\+?\(?\d[\d ()." + DASHES + r"]*\d(?!\w)")
NUMERIC_DATE_RE = re.compile(r"\d{1,2}[./" + DASHES + r"]\d{1,2}[./" + DASHES + r"]\d{4}")
SPACED_THOUSANDS_RE = re.compile(r"\d{1,3}(?: \d{3})+")
ISO_DATE_PREFIX_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
YEAR_RANGE_RE = re.compile(r"\d{4}-\d{4}")

PLACEHOLDERS = {
    "url_userinfo": "[url]",
    "email": "[email]",
    "phone": "[phone]",
}


def _is_phone(candidate):
    """Decide whether a digit candidate looks like a phone number."""
    digits = re.sub(r"\D", "", candidate)
    if not 7 <= len(digits) <= 15:
        return False
    # Plain digit runs (counts, ids) need a separator or a leading plus, except a bare
    # run of exactly 10 or 11 digits.
    if re.fullmatch(r"\d+", candidate):
        return len(digits) in (10, 11)
    if ISO_DATE_PREFIX_RE.match(candidate) or YEAR_RANGE_RE.fullmatch(candidate):
        return False
    if NUMERIC_DATE_RE.fullmatch(candidate) or SPACED_THOUSANDS_RE.fullmatch(candidate):
        return False
    # A single-dot decimal (3.14159265) is a number; only 555.0105 keeps the phone shape.
    if re.fullmatch(r"\d+\.\d+", candidate) and not re.fullmatch(r"\d{3}\.\d{4}", candidate):
        return False
    # Dotted numbers with short groups are versions or IP-like tokens.
    if re.fullmatch(r"\d+(?:\.\d+)+", candidate) and all(len(g) <= 3 for g in candidate.split(".")):
        return False
    return True


LEGAL_SUFFIX_RE = re.compile(r"(?:ltd|limited|inc|llc|gmbh|corp|co|sa|plc)\.?", re.IGNORECASE)


def _term_regex(term, kind="people"):
    """
    Whole-phrase regex for a configured term. Words may be separated by any whitespace
    (including line breaks). A two-word people term also matches "Last, First"; a company
    term also matches without its trailing legal suffix (Ltd, Inc, LLC, ...).
    """
    words = term.split()
    if kind == "companies" and len(words) > 1 and LEGAL_SUFFIX_RE.fullmatch(words[-1]):
        base = r"\s+".join(re.escape(w) for w in words[:-1])
        pattern = base + r"(?:\s+" + LEGAL_SUFFIX_RE.pattern + r")?"
    else:
        pattern = r"\s+".join(re.escape(w) for w in words)
        if kind == "people" and len(words) == 2:
            pattern = "(?:" + pattern + "|" + re.escape(words[1]) + r"\s*,\s*" + re.escape(words[0]) + ")"
    return re.compile(r"(?<!\w)" + pattern + r"(?!\w)", re.IGNORECASE)


def _collect(text, pii_terms, allow_company_names):
    """Return a sorted list of (start, end, type, placeholder, match) with no overlaps."""
    taken = []

    def free(start, end):
        return all(end <= s or start >= e for s, e, _, _, _ in taken)

    def add(regex, ftype, placeholder, accept=None):
        for m in regex.finditer(text):
            if accept is not None and not accept(m.group(0)):
                continue
            if free(m.start(), m.end()):
                taken.append((m.start(), m.end(), ftype, placeholder, m.group(0)))

    add(URL_USERINFO_RE, "url_userinfo", "[url]")
    add(EMAIL_RE, "email", "[email]")
    add(PHONE_RE, "phone", "[phone]", _is_phone)

    terms = pii_terms or {}
    for term in terms.get("people") or []:
        if str(term).strip():
            add(_term_regex(str(term), "people"), "term", "[name]")
    if not allow_company_names:
        for term in terms.get("companies") or []:
            if str(term).strip():
                add(_term_regex(str(term), "companies"), "term", "[company]")

    return sorted(taken)


def scan(text, pii_terms=None, allow_company_names=False):
    """Return findings: [{"type", "match", "line"}] in text order."""
    findings = []
    for start, _end, ftype, _ph, match in _collect(text, pii_terms, allow_company_names):
        findings.append({"type": ftype, "match": match, "line": text.count("\n", 0, start) + 1})
    return findings


def scrub(text, pii_terms=None, allow_company_names=False):
    """Replace PII with [email], [phone], [url], [name] or [company]."""
    out = text
    for start, end, _ftype, placeholder, _match in reversed(_collect(text, pii_terms, allow_company_names)):
        out = out[:start] + placeholder + out[end:]
    return out


def _strip_quotes(value):
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def _simple_config(content):
    """
    Tolerant reader for the two keys we need when PyYAML is missing.
    Understands, under a top-level `anecdotes:` block, `allow_company_names: true|false` and
    `pii_terms` with `people` / `companies` as inline lists ([a, b]) or block lists (- a).
    Anything else is ignored; defaults are no terms and allow_company_names false.
    """
    terms = {"people": [], "companies": []}
    allow = False
    in_block = False
    current = None
    for raw in content.splitlines():
        line = raw.split(" #")[0].rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        stripped = line.strip()
        if indent == 0:
            in_block = stripped.startswith("anecdotes:")
            current = None
            continue
        if not in_block:
            continue
        if stripped.startswith("allow_company_names:"):
            allow = stripped.split(":", 1)[1].strip().lower() == "true"
            continue
        if stripped.startswith("pii_terms:"):
            rest = stripped.split(":", 1)[1].strip()
            for key in ("people", "companies"):
                m = re.search(key + r"\s*:\s*\[([^\]]*)\]", rest)
                if m:
                    terms[key] = [_strip_quotes(x) for x in m.group(1).split(",") if x.strip()]
            continue
        m = re.match(r"(people|companies)\s*:\s*(.*)$", stripped)
        if m:
            current = m.group(1)
            rest = m.group(2).strip()
            if rest.startswith("[") and rest.endswith("]"):
                terms[current] = [_strip_quotes(x) for x in rest[1:-1].split(",") if x.strip()]
                current = None
            continue
        if stripped.startswith("- ") and current:
            terms[current].append(_strip_quotes(stripped[2:]))
    return terms, allow


def load_pii_config(config_path):
    """Read anecdotes.pii_terms and anecdotes.allow_company_names; return (pii_terms, allow)."""
    with open(config_path, "r", encoding="utf-8") as f:
        content = f.read()
    try:
        import yaml
    except ImportError:
        return _simple_config(content)
    data = yaml.safe_load(content) or {}
    section = data.get("anecdotes") or {}
    terms = section.get("pii_terms") or {}
    pii_terms = {
        "people": [str(t) for t in terms.get("people") or []],
        "companies": [str(t) for t in terms.get("companies") or []],
    }
    return pii_terms, bool(section.get("allow_company_names", False))


def _load_config_or_default(config_path):
    if config_path is None:
        config_path = "pm.config.yaml"
        if not os.path.exists(config_path):
            return {"people": [], "companies": []}, False
    return load_pii_config(config_path)


def main(argv):
    usage = "Usage: pii.py scan|scrub <file> [--config pm.config.yaml]"
    if len(argv) < 3 or argv[1] not in ("scan", "scrub"):
        print(usage)
        return 1
    command, file_path = argv[1], argv[2]
    config_path = None
    rest = argv[3:]
    if rest:
        if len(rest) == 2 and rest[0] == "--config":
            config_path = rest[1]
        else:
            print(usage)
            return 1
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            text = f.read()
    except FileNotFoundError:
        print(f"Error: File not found: {file_path}")
        return 1
    except (OSError, UnicodeDecodeError) as e:
        print(f"Error: Cannot read {file_path}: {e}")
        return 1
    try:
        pii_terms, allow = _load_config_or_default(config_path)
    except FileNotFoundError:
        print(f"Error: Config not found: {config_path}")
        return 1
    except Exception as e:
        print(f"Error: Cannot read config {config_path}: {e}")
        return 1

    if command == "scrub":
        sys.stdout.write(scrub(text, pii_terms, allow))
        return 0
    findings = scan(text, pii_terms, allow)
    for f in findings:
        print(f"{file_path}:{f['line']}: {f['type']}: {f['match']}")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
