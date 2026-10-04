#!/usr/bin/env python3
"""
Cost meter: estimate subagent spend from transcripts and compare it with the stage budgets.
Usage:
  python scripts/cost_meter.py log <run_dir> --transcript <path> --agent-type <t> [--agent-id <id>]
  python scripts/cost_meter.py summary <run_dir>
  python scripts/cost_meter.py check <run_dir>
Cost is an estimate: tokens come from the transcript, prices from pm.config.yaml.
"""

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "pm.config.yaml"
COST_LOG = "cost.log.jsonl"
STAGES = ("stage1", "stage2", "stage3")
TOKEN_KEYS = (
    ("input", "input_tokens"),
    ("output", "output_tokens"),
    ("cache_read", "cache_read_input_tokens"),
    ("cache_write", "cache_creation_input_tokens"),
)
PRICE_KEYS = {
    "input": "input_per_mtok",
    "output": "output_per_mtok",
    "cache_read": "cache_read_per_mtok",
    "cache_write": "cache_write_per_mtok",
}


def load_config(path: Path = CONFIG_PATH) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except (OSError, yaml.YAMLError):
        return {}
    return data if isinstance(data, dict) else {}


def model_tier(model: Optional[str]) -> str:
    """Map a model id to small, medium or large. Unknown models are medium."""
    name = (model or "").lower()
    if "haiku" in name:
        return "small"
    if "opus" in name:
        return "large"
    return "medium"


def _valid_tokens(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _valid_usd(value: Any) -> bool:
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and value >= 0)


def parse_transcript(path: str) -> Dict[str, Any]:
    """Return {"tokens": {...} | None, "model": str | None}. Never raises."""
    totals = {name: 0 for name, _ in TOKEN_KEYS}
    model = None
    found = False
    seen = set()
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except OSError:
        return {"tokens": None, "model": None}
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        message = obj.get("message") if isinstance(obj, dict) else None
        if not isinstance(message, dict) or message.get("role") != "assistant":
            continue
        usage = message.get("usage")
        if not isinstance(usage, dict):
            continue
        if any(key in usage and not _valid_tokens(usage[key]) for _, key in TOKEN_KEYS):
            continue  # damaged token values: skip the whole message
        message_id = message.get("id")
        if isinstance(message_id, str) and message_id:
            if message_id in seen:
                continue
            seen.add(message_id)
        found = True
        for name, key in TOKEN_KEYS:
            totals[name] += usage.get(key, 0)
        if isinstance(message.get("model"), str) and message["model"]:
            model = message["model"]
    return {"tokens": totals if found else None, "model": model}


def estimate_usd(tokens: Optional[Dict[str, int]], model: Optional[str], config: Dict[str, Any]) -> Optional[float]:
    """Price tokens with the config table. None when tokens or pricing are missing."""
    if tokens is None:
        return None
    pricing = config.get("pricing")
    if not isinstance(pricing, dict):
        return None
    prices = pricing.get(model_tier(model))
    if not isinstance(prices, dict):
        return None
    total = 0.0
    try:
        for name, key in PRICE_KEYS.items():
            total += tokens[name] * float(prices[key]) / 1_000_000
    except (KeyError, TypeError, ValueError):
        return None
    return round(total, 6)


def read_log_lines(run_dir) -> List[Optional[Dict[str, Any]]]:
    """Every non-blank log line: the entry dict, or None when the line is not a JSON object."""
    entries: List[Optional[Dict[str, Any]]] = []
    try:
        with open(Path(run_dir) / COST_LOG, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    obj = json.loads(line)
                except ValueError:
                    entries.append(None)
                    continue
                entries.append(obj if isinstance(obj, dict) else None)
    except OSError:
        pass
    return entries


def read_log(run_dir) -> List[Dict[str, Any]]:
    return [e for e in read_log_lines(run_dir) if e is not None]


def current_stage(run_dir) -> str:
    try:
        with open(Path(run_dir) / "state.json", "r", encoding="utf-8") as f:
            stage = json.load(f).get("stage")
    except (OSError, ValueError, AttributeError):
        return "unknown"
    return stage if isinstance(stage, str) else "unknown"


def log_entry(run_dir, transcript: str, agent_type: str, agent_id: Optional[str],
              config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Append one cost entry. Returns None when this agent_id (or, without one, this transcript) was already logged."""
    existing = read_log(run_dir)
    if agent_id:
        if any(e.get("agent_id") == agent_id for e in existing):
            return None
    elif any(not e.get("agent_id") and e.get("transcript") == transcript for e in existing):
        return None
    parsed = parse_transcript(transcript)
    tokens = parsed["tokens"]
    usd = estimate_usd(tokens, parsed["model"], config)
    entry = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "stage": current_stage(run_dir),
        "agent_type": agent_type,
        "agent_id": agent_id or None,
        "transcript": transcript,
        "model": parsed["model"],
        "tokens": tokens,
        "estimated_usd": usd,
        "source": "transcript" if tokens is not None else "unparsed",
    }
    with open(Path(run_dir) / COST_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def summarise(run_dir, config: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Per stage: {spent_usd, budget_usd, percent, unparsed}."""
    budgets = config.get("budgets") if isinstance(config.get("budgets"), dict) else {}
    entries = read_log_lines(run_dir)
    now_stage = current_stage(run_dir)
    result = {}
    for stage in STAGES:
        spent = 0.0
        unparsed = 0
        for e in entries:
            if e is None:  # damaged line: its stage is unknown, so charge it to the current stage
                if stage == now_stage:
                    unparsed += 1
                continue
            if e.get("stage") != stage:
                continue
            usd = e.get("estimated_usd")
            if _valid_usd(usd):
                spent += usd
            else:
                unparsed += 1
        budget = budgets.get(stage)
        budget = float(budget) if isinstance(budget, (int, float)) and not isinstance(budget, bool) else None
        if budget is None:
            percent = None
        elif budget > 0:
            percent = round(spent / budget * 100, 6)
        else:
            percent = 100.0 if spent > 0 else 0.0
        result[stage] = {
            "spent_usd": round(spent, 6),
            "budget_usd": budget,
            "percent": percent,
            "unparsed": unparsed,
        }
    return result


def check(run_dir, config: Dict[str, Any]):
    """Return (exit_code, message or None) for the run's current stage."""
    stage = current_stage(run_dir)
    if stage not in STAGES:
        return 0, None
    info = summarise(run_dir, config)[stage]
    percent = info["percent"]
    budgets = config.get("budgets") if isinstance(config.get("budgets"), dict) else {}
    if percent is not None:
        if percent >= 100:
            return 1, f"STOP: {stage} budget exceeded ({info['spent_usd']:.2f} of {info['budget_usd']:.2f})"
        warn_at = budgets.get("warn_at_percent", 80)
        if percent >= warn_at:
            return 0, f"WARN: {stage} at {math.floor(percent)}% of budget"
    reason = None
    if info["unparsed"]:
        reason = f"{info['unparsed']} unparsed entries"
    elif not isinstance(config.get("pricing"), dict):
        reason = "no price table"
    elif percent is None:
        reason = "no budget"
    if reason:
        return 0, f"WARN: {stage} cost cannot be fully estimated ({reason})"
    return 0, None


def _fmt_money(value: Optional[float]) -> str:
    return "n/a" if value is None else f"${value:.2f}"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Estimate subagent cost against stage budgets.")
    sub = parser.add_subparsers(dest="command", required=True)
    p_log = sub.add_parser("log")
    p_log.add_argument("run_dir")
    p_log.add_argument("--transcript", required=True)
    p_log.add_argument("--agent-type", required=True)
    p_log.add_argument("--agent-id", default=None)
    sub.add_parser("summary").add_argument("run_dir")
    sub.add_parser("check").add_argument("run_dir")
    args = parser.parse_args(argv)

    run_dir = Path(args.run_dir)
    if not run_dir.is_dir():
        print(f"Error: run directory not found: {args.run_dir}", file=sys.stderr)
        return 1
    config = load_config()
    try:
        if args.command == "log":
            entry = log_entry(run_dir, args.transcript, args.agent_type, args.agent_id, config)
            if entry is None:
                print(f"Already logged: {args.agent_id}")
            else:
                print(json.dumps(entry))
            return 0
        if args.command == "summary":
            for stage, info in summarise(run_dir, config).items():
                pct = "n/a" if info["percent"] is None else f"{info['percent']:.1f}%"
                line = f"{stage}: spent {_fmt_money(info['spent_usd'])} of {_fmt_money(info['budget_usd'])} ({pct})"
                if info["unparsed"]:
                    line += f", {info['unparsed']} unparsed"
                print(line)
            return 0
        code, message = check(run_dir, config)
        if message:
            print(message)
        return code
    except Exception as e:  # never a traceback
        print(f"Error: {type(e).__name__}: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
