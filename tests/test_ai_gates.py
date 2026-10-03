"""Test ai_gates.py script and compute_verdict function."""

import sys
import json
import subprocess
from pathlib import Path

# Import the function directly for unit tests
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from ai_gates import compute_verdict


def test_all_pass_gives_ai_justified():
    """Test that all five gates passing gives AI_JUSTIFIED."""
    gates = {"1": "pass", "2": "pass", "3": "pass", "4": "pass", "5": "pass"}
    red_flags = []

    verdict = compute_verdict(gates, red_flags)
    assert verdict == "AI_JUSTIFIED"


def test_one_fail_gives_not_justified():
    """Test that one failed gate gives AI_NOT_JUSTIFIED."""
    gates = {"1": "pass", "2": "fail", "3": "pass", "4": "pass", "5": "pass"}
    red_flags = []

    verdict = compute_verdict(gates, red_flags)
    assert verdict == "AI_NOT_JUSTIFIED"


def test_one_unknown_gives_needs_data():
    """Test that one unknown gate (with no fails) gives NEEDS_DATA."""
    gates = {"1": "pass", "2": "unknown", "3": "pass", "4": "pass", "5": "pass"}
    red_flags = []

    verdict = compute_verdict(gates, red_flags)
    assert verdict == "NEEDS_DATA"


def test_red_flag_overrides_all_pass():
    """Test that a red flag beats all gates passing."""
    gates = {"1": "pass", "2": "pass", "3": "pass", "4": "pass", "5": "pass"}
    red_flags = ["known_finite_rules"]

    verdict = compute_verdict(gates, red_flags)
    assert verdict == "AI_NOT_JUSTIFIED"


def test_fail_beats_unknown():
    """Test that fail beats unknown in verdict."""
    gates = {"1": "fail", "2": "unknown", "3": "pass", "4": "pass", "5": "pass"}
    red_flags = []

    verdict = compute_verdict(gates, red_flags)
    assert verdict == "AI_NOT_JUSTIFIED"


def test_multiple_unknowns():
    """Test that multiple unknowns still gives NEEDS_DATA (no fails)."""
    gates = {"1": "unknown", "2": "unknown", "3": "pass", "4": "pass", "5": "pass"}
    red_flags = []

    verdict = compute_verdict(gates, red_flags)
    assert verdict == "NEEDS_DATA"


def test_multiple_red_flags():
    """Test that multiple red flags give AI_NOT_JUSTIFIED."""
    gates = {"1": "pass", "2": "pass", "3": "pass", "4": "pass", "5": "pass"}
    red_flags = ["insufficient_data", "catastrophic_errors"]

    verdict = compute_verdict(gates, red_flags)
    assert verdict == "AI_NOT_JUSTIFIED"


def test_missing_gates_raises_error():
    """Test that missing a gate key raises ValueError."""
    gates = {"1": "pass", "2": "pass", "3": "pass", "4": "pass"}  # missing 5
    red_flags = []

    try:
        compute_verdict(gates, red_flags)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "gates must have exactly keys" in str(e)


def test_invalid_gate_result_raises_error():
    """Test that an invalid gate result raises ValueError."""
    gates = {"1": "pass", "2": "maybe", "3": "pass", "4": "pass", "5": "pass"}
    red_flags = []

    try:
        compute_verdict(gates, red_flags)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "invalid result" in str(e)


def test_invalid_red_flag_raises_error():
    """Test that an invalid red flag raises ValueError."""
    gates = {"1": "pass", "2": "pass", "3": "pass", "4": "pass", "5": "pass"}
    red_flags = ["unknown_flag"]

    try:
        compute_verdict(gates, red_flags)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "unknown red flag" in str(e)


def test_cli_with_json_input():
    """Test the CLI with JSON input."""
    input_data = {
        "gates": {"1": "pass", "2": "pass", "3": "pass", "4": "pass", "5": "pass"},
        "red_flags": []
    }

    result = subprocess.run(
        [sys.executable, "scripts/ai_gates.py"],
        input=json.dumps(input_data).encode(),
        capture_output=True,
        cwd=Path(__file__).parent.parent
    )

    assert result.returncode == 0
    output = json.loads(result.stdout.decode())
    assert output["verdict"] == "AI_JUSTIFIED"


def test_cli_with_fail_verdict():
    """Test the CLI with a failing gate."""
    input_data = {
        "gates": {"1": "pass", "2": "fail", "3": "pass", "4": "pass", "5": "pass"},
        "red_flags": []
    }

    result = subprocess.run(
        [sys.executable, "scripts/ai_gates.py"],
        input=json.dumps(input_data).encode(),
        capture_output=True,
        cwd=Path(__file__).parent.parent
    )

    assert result.returncode == 0
    output = json.loads(result.stdout.decode())
    assert output["verdict"] == "AI_NOT_JUSTIFIED"


def test_cli_with_invalid_json():
    """Test that invalid JSON input fails gracefully."""
    result = subprocess.run(
        [sys.executable, "scripts/ai_gates.py"],
        input=b"invalid json",
        capture_output=True,
        cwd=Path(__file__).parent.parent
    )

    assert result.returncode == 1
    assert b"Invalid JSON" in result.stderr


def test_cli_with_json_list_input():
    """Test that top-level JSON list exits 1 with clear message and no traceback."""
    input_data = ["pass", "fail", "pass", "pass", "pass"]

    result = subprocess.run(
        [sys.executable, "scripts/ai_gates.py"],
        input=json.dumps(input_data).encode(),
        capture_output=True,
        cwd=Path(__file__).parent.parent
    )

    assert result.returncode == 1
    assert b"Error" in result.stderr
    # Should not have traceback
    assert b"Traceback" not in result.stderr


def test_cli_with_object_valued_gate():
    """Test that an object-valued gate (when should be string) exits 1."""
    input_data = {
        "gates": {"1": {"nested": "object"}, "2": "pass", "3": "pass", "4": "pass", "5": "pass"},
        "red_flags": []
    }

    result = subprocess.run(
        [sys.executable, "scripts/ai_gates.py"],
        input=json.dumps(input_data).encode(),
        capture_output=True,
        cwd=Path(__file__).parent.parent
    )

    assert result.returncode == 1
    assert b"Error" in result.stderr or b"error" in result.stderr.lower()
    # Should not have traceback
    assert b"Traceback" not in result.stderr


def test_list_red_flag_raises_error():
    """Test that a red flag that is a list raises ValueError."""
    gates = {"1": "pass", "2": "pass", "3": "pass", "4": "pass", "5": "pass"}
    red_flags = [["nested", "list"]]

    try:
        compute_verdict(gates, red_flags)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "must contain only strings" in str(e)


def test_object_red_flag_raises_error():
    """Test that a red flag that is an object raises ValueError."""
    gates = {"1": "pass", "2": "pass", "3": "pass", "4": "pass", "5": "pass"}
    red_flags = [{"nested": "object"}]

    try:
        compute_verdict(gates, red_flags)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "must contain only strings" in str(e)


def test_cli_with_list_red_flag():
    """Test that a list-valued red flag exits 1 with clear message and no traceback."""
    input_data = {
        "gates": {"1": "pass", "2": "pass", "3": "pass", "4": "pass", "5": "pass"},
        "red_flags": [["nested", "list"]]
    }

    result = subprocess.run(
        [sys.executable, "scripts/ai_gates.py"],
        input=json.dumps(input_data).encode(),
        capture_output=True,
        cwd=Path(__file__).parent.parent
    )

    assert result.returncode == 1
    assert b"Error" in result.stderr
    assert b"Traceback" not in result.stderr


def test_cli_with_object_red_flag():
    """Test that an object-valued red flag exits 1 with clear message and no traceback."""
    input_data = {
        "gates": {"1": "pass", "2": "pass", "3": "pass", "4": "pass", "5": "pass"},
        "red_flags": [{"nested": "object"}]
    }

    result = subprocess.run(
        [sys.executable, "scripts/ai_gates.py"],
        input=json.dumps(input_data).encode(),
        capture_output=True,
        cwd=Path(__file__).parent.parent
    )

    assert result.returncode == 1
    assert b"Error" in result.stderr
    assert b"Traceback" not in result.stderr
