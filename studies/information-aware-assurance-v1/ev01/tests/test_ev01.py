import ast
import json
from copy import deepcopy
from pathlib import Path

import pytest

from ev01 import check
from ev01 import verify as frozen


@pytest.fixture(scope="module")
def reference():
    return check.exercise()


def test_all_reference_vectors(reference):
    assert reference["reference_vectors_pass"]
    rows = reference["reference_vectors"]
    assert len(rows) == 17 and len({r["name"] for r in rows}) == 17
    assert all(r["passed"] for r in rows)
    assert reference["external_integration_confirmed"] is False
    assert reference["independence_not_assessed"] is True
    assert reference["physical_validation"] is False


@pytest.mark.parametrize(
    "name",
    ["A1_exponent_rejected", "future_2", "future_3", "old_component_version", "incompatible_frame"],
)
def test_required_public_rejections(reference, name):
    rows = {r["name"]: r for r in reference["reference_vectors"]}
    assert rows[name]["receipt"]["result"]["status"] == "unsupported_input"


def test_stale_and_expiry_have_distinct_meanings(reference):
    rows = {r["name"]: r for r in reference["reference_vectors"]}
    stale = rows["stale_prediction"]["receipt"]["result"]
    assert stale["checked"]["uncertainty"]["status"] == "prediction_only_missing_or_stale"
    expired = rows["expired_credit"]["receipt"]["result"]
    assert expired["simulated_output"]["credited"] is False


def test_actual_callback_and_readonly_snapshot():
    seen = []

    def proposal(snapshot):
        seen.append(deepcopy(snapshot))
        snapshot["at_ms"] = 99999
        return ["0", "1/100"]

    result = check.exercise(proposal)
    assert len(seen) == 2 and seen[0]["packets"] != seen[1]["packets"]
    assert all(r["executed"] and r["replayed"] for r in result["controller_cases"])
    for row in result["controller_cases"]:
        assert row["receipt"]["request"]["proposed_action"] == ["0", "1/100"]
        assert row["receipt"]["request"]["current_input"]["at_ms"] == 650
    assert result["external_integration_confirmed"] is False


@pytest.mark.parametrize("action", [[True, 0], [float("nan"), 0], [0], object()])
def test_callback_failures_retained(action):
    result = check.exercise(lambda _: action)
    assert len(result["controller_cases"]) == 2
    assert all(r["executed"] is False for r in result["controller_cases"])
    assert result["external_integration_confirmed"] is False


def test_callback_error_retained():
    def bad(_):
        raise RuntimeError("diagnostic")

    result = check.exercise(bad)
    assert all(r["error"] == "RuntimeError" for r in result["controller_cases"])


def test_output_never_overwrites_and_checksums(tmp_path):
    output = tmp_path / "result"
    assert check.execute(output) == 0
    original = (output / "results.json").read_bytes()
    with pytest.raises(FileExistsError):
        check.execute(output)
    assert (output / "results.json").read_bytes() == original
    for name, expected in json.loads((output / "checksums.json").read_text()).items():
        assert check.digest(output / name) == expected


def test_missing_callback_function_retains_environment(tmp_path):
    source = tmp_path / "controller.py"
    source.write_text("x = 1\n")
    output = tmp_path / "report"
    assert check.execute(output, source) == 1
    assert (output / "environment.json").exists()
    assert json.loads((output / "results.json").read_text())["fatal_error"] == "AttributeError"


def test_version_mismatch_does_not_pass(monkeypatch):
    from kri_assurance_eval import api

    original = api.contract

    def wrong():
        value = original()
        value["component_version"] = "0.1.0"
        return value

    monkeypatch.setattr(api, "contract", wrong)
    with pytest.raises(ValueError):
        check.exercise()


def test_runner_uses_public_interfaces():
    tree = ast.parse(Path(check.__file__).read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert "_vendor" not in (node.module or "")
            assert not (node.module or "").startswith(("sa02", "sa03", "sa04", "sa05"))


def test_permissions_and_scope_are_explicit():
    text = (check.HERE / "REPORT_TEMPLATE.md").read_text()
    assert "Default NO" in text and "personally install" in text
    protocol = json.loads((check.HERE / "protocol.json").read_text())
    assert protocol["maximum_initial_recipients"] <= 8
    assert protocol["external_evidence_automatically_certified"] is False
    assert protocol["hardware"] is False


@pytest.mark.skipif(not (check.HERE / "freeze.json").exists(), reason="Pre-freeze preparation")
def test_final_protocol_binding():
    result = frozen.verify()
    assert result["passed"] and result["external_execution"] is False


@pytest.mark.skipif(not (check.HERE / "freeze.json").exists(), reason="Pre-freeze preparation")
def test_forged_git_anchor_fails(monkeypatch):
    original = frozen.git

    def changed(*args):
        result = original(*args)
        return (
            result + b"changed" if args[0] == "show" and args[1].endswith("freeze.json") else result
        )

    monkeypatch.setattr(frozen, "git", changed)
    with pytest.raises(ValueError):
        frozen.verify()
