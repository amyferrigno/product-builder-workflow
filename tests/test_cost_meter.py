"""Test scripts/cost_meter.py: parsing, pricing, logging, summary and budget check."""

import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import cost_meter  # noqa: E402
from cost_helpers import (  # noqa: E402
    REPO_ROOT, TRANSCRIPTS, make_project, make_run, read_log, run_meter, write_log,
)

CONFIG = cost_meter.load_config(REPO_ROOT / "pm.config.yaml")


def test_config_has_pricing_with_expected_values():
    pricing = CONFIG["pricing"]
    assert (pricing["small"]["input_per_mtok"], pricing["small"]["output_per_mtok"]) == (1, 5)
    assert (pricing["medium"]["input_per_mtok"], pricing["medium"]["output_per_mtok"]) == (3, 15)
    assert (pricing["large"]["input_per_mtok"], pricing["large"]["output_per_mtok"]) == (15, 75)
    for tier in pricing.values():
        assert tier["cache_read_per_mtok"] == pytest.approx(tier["input_per_mtok"] / 10)
        assert tier["cache_write_per_mtok"] == pytest.approx(tier["input_per_mtok"] * 1.25)


@pytest.mark.parametrize("model,tier", [
    ("claude-haiku-4-5", "small"),
    ("claude-sonnet-4-5", "medium"),
    ("claude-opus-4-1", "large"),
    ("some-other-model", "medium"),
    (None, "medium"),
])
def test_model_tier(model, tier):
    assert cost_meter.model_tier(model) == tier


def test_parse_normal_sums_tokens_and_dedupes_message_ids():
    parsed = cost_meter.parse_transcript(str(TRANSCRIPTS / "normal.jsonl"))
    assert parsed["tokens"] == {"input": 1200, "output": 600, "cache_read": 2000, "cache_write": 400}
    assert parsed["model"] == "claude-sonnet-4-5"


def test_parse_without_usage_and_not_jsonl_give_none():
    assert cost_meter.parse_transcript(str(TRANSCRIPTS / "no_usage.jsonl"))["tokens"] is None
    assert cost_meter.parse_transcript(str(TRANSCRIPTS / "not_jsonl.txt"))["tokens"] is None
    assert cost_meter.parse_transcript(str(TRANSCRIPTS / "missing.jsonl"))["tokens"] is None


def test_estimate_medium_includes_cache_pricing():
    parsed = cost_meter.parse_transcript(str(TRANSCRIPTS / "normal.jsonl"))
    # 1200*3 + 600*15 + 2000*0.3 + 400*3.75 = 3600 + 9000 + 600 + 1500 = 14700 per million
    assert cost_meter.estimate_usd(parsed["tokens"], parsed["model"], CONFIG) == pytest.approx(0.0147)


def test_estimate_opus_uses_large_tier():
    parsed = cost_meter.parse_transcript(str(TRANSCRIPTS / "opus.jsonl"))
    # 15 + 7.5 + 1.5 + 1.875
    assert cost_meter.estimate_usd(parsed["tokens"], parsed["model"], CONFIG) == pytest.approx(25.875)


def test_estimate_none_without_pricing_block():
    config = {k: v for k, v in CONFIG.items() if k != "pricing"}
    assert cost_meter.estimate_usd({"input": 1, "output": 1, "cache_read": 1, "cache_write": 1}, "x", config) is None


def test_log_writes_expected_entry(tmp_path):
    project = make_project(tmp_path)
    run = make_run(project, stage="stage2")
    result = run_meter(project, "log", str(run), "--transcript", str(TRANSCRIPTS / "normal.jsonl"),
                       "--agent-type", "prd-writer", "--agent-id", "agent-1")
    assert result.returncode == 0, result.stderr
    entries = read_log(run)
    assert len(entries) == 1
    entry = entries[0]
    assert entry["stage"] == "stage2"
    assert entry["agent_type"] == "prd-writer"
    assert entry["agent_id"] == "agent-1"
    assert entry["model"] == "claude-sonnet-4-5"
    assert entry["tokens"] == {"input": 1200, "output": 600, "cache_read": 2000, "cache_write": 400}
    assert entry["estimated_usd"] == pytest.approx(0.0147)
    assert entry["source"] == "transcript"
    assert re.match(r"^\d{4}-\d\d-\d\dT", entry["ts"])


def test_same_agent_id_is_never_logged_twice(tmp_path):
    project = make_project(tmp_path)
    run = make_run(project)
    args = ["log", str(run), "--transcript", str(TRANSCRIPTS / "normal.jsonl"),
            "--agent-type", "x", "--agent-id", "agent-1"]
    assert run_meter(project, *args).returncode == 0
    assert run_meter(project, *args).returncode == 0
    assert len(read_log(run)) == 1


@pytest.mark.parametrize("name", ["no_usage.jsonl", "not_jsonl.txt", "missing.jsonl"])
def test_unparseable_transcript_logs_null_values(tmp_path, name):
    project = make_project(tmp_path)
    run = make_run(project)
    result = run_meter(project, "log", str(run), "--transcript", str(TRANSCRIPTS / name), "--agent-type", "x")
    assert result.returncode == 0, result.stderr
    entry = read_log(run)[0]
    assert entry["tokens"] is None
    assert entry["estimated_usd"] is None
    assert entry["source"] == "unparsed"


def test_missing_pricing_logs_tokens_without_estimate(tmp_path):
    config = (REPO_ROOT / "pm.config.yaml").read_text(encoding="utf-8")
    config = re.sub(r"# Prices in USD.*?(?=^audit:)", "", config, flags=re.S | re.M)
    assert "pricing" not in config
    project = make_project(tmp_path, config_text=config)
    run = make_run(project)
    run_meter(project, "log", str(run), "--transcript", str(TRANSCRIPTS / "normal.jsonl"), "--agent-type", "x")
    entry = read_log(run)[0]
    assert entry["tokens"]["input"] == 1200
    assert entry["estimated_usd"] is None
    assert entry["source"] == "transcript"


def test_unknown_run_dir_exits_1_with_one_line(tmp_path):
    project = make_project(tmp_path)
    for args in (["log", str(tmp_path / "nope"), "--transcript", "t", "--agent-type", "x"],
                 ["summary", str(tmp_path / "nope")], ["check", str(tmp_path / "nope")]):
        result = run_meter(project, *args)
        assert result.returncode == 1
        assert "Traceback" not in result.stderr
        assert len((result.stdout + result.stderr).strip().splitlines()) == 1


def _entry(stage, usd):
    return {"ts": "2026-10-04T00:00:00Z", "stage": stage, "agent_type": "x", "agent_id": None, "model": None,
            "tokens": None if usd is None else {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0},
            "estimated_usd": usd, "source": "unparsed" if usd is None else "transcript"}


def test_summarise_per_stage_with_unparsed(tmp_path):
    run = make_run(make_project(tmp_path))
    write_log(run, [_entry("stage1", 1.5), _entry("stage1", 0.5), _entry("stage1", None), _entry("stage2", 1.0)])
    summary = cost_meter.summarise(run, CONFIG)
    assert summary["stage1"] == {"spent_usd": 2.0, "budget_usd": 3.0, "percent": pytest.approx(66.666667), "unparsed": 1}
    assert summary["stage2"]["spent_usd"] == 1.0
    assert summary["stage2"]["percent"] == pytest.approx(50.0)
    assert summary["stage3"] == {"spent_usd": 0.0, "budget_usd": 1.0, "percent": 0.0, "unparsed": 0}


def test_summary_cli_prints_each_stage(tmp_path):
    project = make_project(tmp_path)
    run = make_run(project)
    write_log(run, [_entry("stage1", 1.5)])
    result = run_meter(project, "summary", str(run))
    assert result.returncode == 0
    lines = result.stdout.strip().splitlines()
    assert [line.split(":")[0] for line in lines] == ["stage1", "stage2", "stage3"]
    assert "$1.50 of $3.00 (50.0%)" in lines[0]


@pytest.mark.parametrize("spent,code,expected", [
    (0.0, 0, ""),
    (2.37, 0, ""),                                          # 79 percent
    (2.40, 0, "WARN: stage1 at 80% of budget"),             # 80 percent
    (2.99, 0, "WARN: stage1 at 99% of budget"),
    (3.00, 1, "STOP: stage1 budget exceeded (3.00 of 3.00)"),  # 100 percent
    (3.60, 1, "STOP: stage1 budget exceeded (3.60 of 3.00)"),
])
def test_check_thresholds(tmp_path, spent, code, expected):
    project = make_project(tmp_path)
    run = make_run(project)
    if spent:
        write_log(run, [_entry("stage1", spent)])
    result = run_meter(project, "check", str(run))
    assert result.returncode == code
    assert result.stdout.strip() == expected


def test_check_stage_done_exits_0_silent(tmp_path):
    project = make_project(tmp_path)
    run = make_run(project, stage="done")
    write_log(run, [_entry("stage1", 99.0), _entry("done", 99.0)])
    result = run_meter(project, "check", str(run))
    assert result.returncode == 0
    assert result.stdout == ""


def test_check_uses_only_the_current_stage(tmp_path):
    project = make_project(tmp_path)
    run = make_run(project, stage="stage2")
    write_log(run, [_entry("stage1", 5.0)])
    assert run_meter(project, "check", str(run)).returncode == 0


def test_null_entries_add_no_spend_but_warn_unparsed(tmp_path):
    project = make_project(tmp_path)
    run = make_run(project)
    write_log(run, [_entry("stage1", None), _entry("stage1", None)])
    result = run_meter(project, "check", str(run))
    assert result.returncode == 0
    assert result.stdout.strip() == "WARN: stage1 cost cannot be fully estimated (2 unparsed entries)"


def _write_raw_log(run, lines):
    (run / "cost.log.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


@pytest.mark.parametrize("bad_line", [
    "not json",
    "[1, 2]",
    "42",
    json.dumps(_entry("stage1", -1.0)),
    json.dumps({**_entry("stage1", 1.0), "estimated_usd": "1.0"}),
    json.dumps({**_entry("stage1", 1.0), "estimated_usd": True}),
])
def test_damaged_log_line_counts_as_unparsed(tmp_path, bad_line):
    run = make_run(make_project(tmp_path))
    _write_raw_log(run, [json.dumps(_entry("stage1", 0.5)), bad_line])
    summary = cost_meter.summarise(run, CONFIG)
    assert summary["stage1"]["unparsed"] == 1
    assert summary["stage1"]["spent_usd"] == 0.5


def test_check_warns_on_damaged_line_and_still_stops_on_parsed_part(tmp_path):
    project = make_project(tmp_path)
    run = make_run(project)
    _write_raw_log(run, ["garbage", json.dumps(_entry("stage1", 0.5))])
    result = run_meter(project, "check", str(run))
    assert result.returncode == 0
    assert result.stdout.strip() == "WARN: stage1 cost cannot be fully estimated (1 unparsed entries)"
    _write_raw_log(run, ["garbage", json.dumps(_entry("stage1", 3.5))])
    result = run_meter(project, "check", str(run))
    assert result.returncode == 1
    assert result.stdout.startswith("STOP: stage1 budget exceeded")
    _write_raw_log(run, ["garbage", json.dumps(_entry("stage1", 2.5))])
    assert run_meter(project, "check", str(run)).stdout.startswith("WARN: stage1 at 83%")


def test_check_ignores_unparsed_entries_of_other_stages(tmp_path):
    project = make_project(tmp_path)
    run = make_run(project, stage="stage2")
    write_log(run, [_entry("stage1", None)])
    assert run_meter(project, "check", str(run)).stdout == ""


def test_check_warns_when_config_is_missing_or_blocks_absent(tmp_path):
    config = (REPO_ROOT / "pm.config.yaml").read_text(encoding="utf-8")
    no_budget = re.sub(r"^budgets:.*?(?=^# Prices in USD)", "", config, flags=re.S | re.M)
    no_pricing = re.sub(r"# Prices in USD.*?(?=^audit:)", "", config, flags=re.S | re.M)
    assert "budgets" not in no_budget and "pricing" not in no_pricing
    for text, reason in ((no_budget, "no budget"), (no_pricing, "no price table"), ("a: [unclosed", "no price table")):
        root = tmp_path / f"{reason.replace(' ', '_')}-{len(text)}"
        root.mkdir()
        project = make_project(root, config_text=text)
        run = make_run(project)
        write_log(run, [_entry("stage1", 1.0)])
        result = run_meter(project, "check", str(run))
        assert result.returncode == 0
        assert result.stdout.strip() == f"WARN: stage1 cost cannot be fully estimated ({reason})"


def test_check_missing_config_file_warns(tmp_path):
    project = make_project(tmp_path)
    (project / "pm.config.yaml").unlink()
    run = make_run(project)
    result = run_meter(project, "check", str(run))
    assert result.returncode == 0
    assert result.stdout.strip() == "WARN: stage1 cost cannot be fully estimated (no price table)"


def _write_transcript(path, messages):
    path.write_text("".join(json.dumps({"type": "x", "message": m}) + "\n" for m in messages), encoding="utf-8")


def _msg(role, usage, mid):
    message = {"id": mid, "model": "claude-sonnet-4-5", "usage": usage}
    if role is not None:
        message["role"] = role
    return message


def test_transcript_counts_only_assistant_messages(tmp_path):
    path = tmp_path / "t.jsonl"
    usage = {"input_tokens": 10, "output_tokens": 5}
    _write_transcript(path, [_msg("assistant", usage, "a"), _msg("user", usage, "b"), _msg(None, usage, "c")])
    assert cost_meter.parse_transcript(str(path))["tokens"]["input"] == 10


@pytest.mark.parametrize("bad", [-1, 1.5, "7", None, True])
def test_transcript_skips_message_with_damaged_token_values(tmp_path, bad):
    path = tmp_path / "t.jsonl"
    good = {"input_tokens": 10, "output_tokens": 5}
    _write_transcript(path, [_msg("assistant", good, "a"), _msg("assistant", {"input_tokens": bad, "output_tokens": 99}, "b")])
    tokens = cost_meter.parse_transcript(str(path))["tokens"]
    assert tokens["input"] == 10 and tokens["output"] == 5


def test_transcript_with_every_message_damaged_is_unparsed(tmp_path):
    project = make_project(tmp_path)
    run = make_run(project)
    path = tmp_path / "t.jsonl"
    _write_transcript(path, [_msg("assistant", {"input_tokens": -5}, "a")])
    assert cost_meter.parse_transcript(str(path))["tokens"] is None
    run_meter(project, "log", str(run), "--transcript", str(path), "--agent-type", "x")
    assert read_log(run)[0]["source"] == "unparsed"


def test_entry_without_agent_id_is_deduplicated_by_transcript_path(tmp_path):
    project = make_project(tmp_path)
    run = make_run(project)
    args = ["log", str(run), "--transcript", str(TRANSCRIPTS / "normal.jsonl"), "--agent-type", "x"]
    run_meter(project, *args)
    result = run_meter(project, *args)
    assert result.returncode == 0
    assert len(read_log(run)) == 1
    run_meter(project, "log", str(run), "--transcript", str(TRANSCRIPTS / "opus.jsonl"), "--agent-type", "x")
    assert len(read_log(run)) == 2


def test_log_then_check_end_to_end_stops_on_opus(tmp_path):
    project = make_project(tmp_path)
    run = make_run(project)
    run_meter(project, "log", str(run), "--transcript", str(TRANSCRIPTS / "opus.jsonl"), "--agent-type", "x")
    result = run_meter(project, "check", str(run))
    assert result.returncode == 1
    assert result.stdout.strip() == "STOP: stage1 budget exceeded (25.88 of 3.00)"
    assert json.loads((run / "cost.log.jsonl").read_text().splitlines()[0])["estimated_usd"] == pytest.approx(25.875)


def test_pricing_schema_rejects_negative_and_unknown_keys():
    import yaml
    from jsonschema import Draft202012Validator
    schema = json.loads((REPO_ROOT / "schemas" / "pm-config.schema.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    base = yaml.safe_load((REPO_ROOT / "pm.config.yaml").read_text(encoding="utf-8"))
    assert list(validator.iter_errors(base)) == []
    base["pricing"]["small"]["input_per_mtok"] = -1
    assert list(validator.iter_errors(base))
    base["pricing"]["small"]["input_per_mtok"] = 1
    base["pricing"]["huge"] = base["pricing"]["small"]
    assert list(validator.iter_errors(base))


def test_log_entry_does_not_write_through_a_symlink(tmp_path):
    run = make_run(make_project(tmp_path / "project"))
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"keep me\n")
    (run / "cost.log.jsonl").symlink_to(outside)
    entry = cost_meter.log_entry(run, str(TRANSCRIPTS / "normal.jsonl"), "x", "agent-1", CONFIG)
    assert entry is None
    assert outside.read_bytes() == b"keep me\n"


def test_cli_log_with_symlinked_log_exits_0_and_leaves_target_alone(tmp_path):
    project = make_project(tmp_path / "project")
    run = make_run(project)
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"keep me\n")
    (run / "cost.log.jsonl").symlink_to(outside)
    result = run_meter(project, "log", str(run), "--transcript", str(TRANSCRIPTS / "normal.jsonl"),
                       "--agent-type", "x")
    assert result.returncode == 0
    assert outside.read_bytes() == b"keep me\n"
    assert result.stdout.strip() == "Skipped: cost log is a symlink"


def test_warn_and_stop_mention_unparsed_entries_not_counted(tmp_path):
    project = make_project(tmp_path)
    run = make_run(project)
    write_log(run, [_entry("stage1", None), _entry("stage1", 2.5)])
    result = run_meter(project, "check", str(run))
    assert result.returncode == 0
    assert result.stdout.strip() == "WARN: stage1 at 83% of budget (1 unparsed entries not counted)"
    write_log(run, [_entry("stage1", None), _entry("stage1", 3.5)])
    result = run_meter(project, "check", str(run))
    assert result.returncode == 1
    assert result.stdout.strip() == "STOP: stage1 budget exceeded (3.50 of 3.00) (1 unparsed entries not counted)"


def test_warn_without_unparsed_entries_has_no_suffix(tmp_path):
    project = make_project(tmp_path)
    run = make_run(project)
    write_log(run, [_entry("stage1", 2.5)])
    assert run_meter(project, "check", str(run)).stdout.strip() == "WARN: stage1 at 83% of budget"
