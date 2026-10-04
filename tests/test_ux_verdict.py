"""Test scripts/ux_verdict.py (compute_ux_verdict)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).parent))
from ux_verdict import compute_ux_verdict, load_ux_rubric

RUBRIC = load_ux_rubric()
HASH = "abc"
BASE = ["req_coverage", "required_states", "accessibility", "token_consistency", "copy_clarity"]
AI = "ai_trust_control_recovery"


def make_audit(ai=False, scores=None, ux_hash=HASH):
    scores = scores or {}
    ids = BASE + ([AI] if ai else [])
    return {
        "run_id": "r", "ux_hash": ux_hash, "ai_feature": ai,
        "dimensions": [{"id": d, "score": scores.get(d, 4), "justification": "x"} for d in ids],
    }


def verdict(audit, has_ai=False, errors=None, current=HASH):
    return compute_ux_verdict(audit, RUBRIC, current, has_ai, errors or [])


def test_all_fours_is_pass():
    assert verdict(make_audit()) == ("PASS", [])


def test_score_two_is_pass_with_risk():
    v, _ = verdict(make_audit(scores={"copy_clarity": 2}))
    assert v == "PASS_WITH_RISK"


def test_score_one_is_fail():
    v, reasons = verdict(make_audit(scores={"copy_clarity": 1}))
    assert v == "FAIL"
    assert any("copy_clarity" in r for r in reasons)


def test_blocking_dimension_below_three_is_fail():
    v, reasons = verdict(make_audit(scores={"req_coverage": 2}))
    assert v == "FAIL"
    assert any("Blocking dimension req_coverage" in r for r in reasons)


def test_non_blocking_three_is_pass():
    assert verdict(make_audit(scores={"accessibility": 3}))[0] == "PASS"


def test_missing_dimension_is_fail():
    audit = make_audit()
    audit["dimensions"] = [d for d in audit["dimensions"] if d["id"] != "accessibility"]
    v, reasons = verdict(audit)
    assert v == "FAIL"
    assert "Missing required dimension: accessibility" in reasons


def test_duplicate_dimension_is_fail():
    audit = make_audit()
    audit["dimensions"].append(dict(audit["dimensions"][0]))
    v, reasons = verdict(audit)
    assert v == "FAIL"
    assert "Duplicate dimension: req_coverage" in reasons


def test_stale_ux_hash_is_fail():
    v, reasons = verdict(make_audit(ux_hash="old"))
    assert v == "FAIL"
    assert any("UX hash mismatch" in r for r in reasons)


def test_ai_feature_mismatch_audit_true_prd_false():
    v, reasons = verdict(make_audit(ai=True), has_ai=False)
    assert v == "FAIL"
    assert any("ai_feature mismatch" in r for r in reasons)


def test_ai_feature_mismatch_audit_false_prd_true():
    v, reasons = verdict(make_audit(ai=False), has_ai=True)
    assert v == "FAIL"
    assert any("ai_feature mismatch" in r for r in reasons)


def test_ai_dimension_required_for_ai_feature():
    audit = make_audit(ai=True)
    audit["dimensions"] = [d for d in audit["dimensions"] if d["id"] != AI]
    v, reasons = verdict(audit, has_ai=True)
    assert v == "FAIL"
    assert f"Missing required dimension: {AI}" in reasons


def test_ai_dimension_not_required_without_ai():
    assert verdict(make_audit(ai=False), has_ai=False)[0] == "PASS"


def test_ai_dimension_blocking_for_ai_feature():
    v, reasons = verdict(make_audit(ai=True, scores={AI: 2}), has_ai=True)
    assert v == "FAIL"
    assert any(AI in r for r in reasons)


def test_ai_dimension_ignored_when_not_ai_feature():
    audit = make_audit(ai=False)
    audit["dimensions"].append({"id": AI, "score": 1, "justification": "x"})
    assert verdict(audit)[0] == "PASS"


def test_validator_errors_force_fail_even_with_all_fours():
    v, reasons = verdict(make_audit(), errors=["screens/SCR-001-home.html: missing state 'error'"])
    assert v == "FAIL"
    assert reasons == ["Script check: screens/SCR-001-home.html: missing state 'error'"]


def test_rubric_dimensions_and_flags():
    dims = {d["id"]: d for d in RUBRIC["dimensions"]}
    assert list(dims) == ["req_coverage", "required_states", AI, "accessibility", "token_consistency", "copy_clarity"]
    assert [i for i, d in dims.items() if d["blocking"]] == ["req_coverage", "required_states", AI]
    assert [i for i, d in dims.items() if d["ai_only"]] == [AI]
    assert all(set(d["scores"]) == {1, 2, 3, 4} for d in dims.values())
