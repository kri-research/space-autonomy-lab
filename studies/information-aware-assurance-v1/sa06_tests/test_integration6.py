import ast
import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest

from iaa.types import identity, primitive
from sa04.compute import check_action


@pytest.mark.parametrize("index", range(10))
def test_documented_inputs(component, index):
    from kri_assurance_eval.examples import examples

    item = examples()[index]
    actual = component.assess(item["request"])
    assert actual["status"] == item["expected_status"]
    assert not any(
        actual[k]
        for k in (
            "physical_actuation",
            "full_recovery",
            "conformance_claim",
            "realtime_claim",
            "external_validation",
            "transferable_authority",
        )
    )


def test_original_checker_unchanged_by_relocation(component, request_data):
    for action in (["0", "0"], ["0", "1/50"], ["-1/50", "0"]):
        request_data["proposed_action"] = action
        expected, _ = check_action(dict(input=request_data["current_input"], action=action))
        actual = component.assess(request_data)
        assert actual["checked"] == primitive(expected)
        assert actual["candidate_applied_in_simulation"]


def test_zero_is_not_an_effective_intervention(component, request_data):
    request_data["proposed_action"] = ["0", "0"]
    actual = component.assess(request_data)
    assert actual["status"] == "supported_prefix"
    assert not actual["effective_change_from_coast"]
    assert actual["simulated_output"]["expires_ms"] == 4200


@pytest.mark.parametrize(
    "ready,apply,status",
    [
        (701, 700, "late"),
        (650, 710, "supported_prefix"),
        (600, 700, "rejected_binding"),
        (675, 711, "missed_application_window"),
        (675, 4200, "missed_application_window"),
        (675, 5000, "unsupported_input"),
    ],
)
def test_time_boundaries(component, request_data, ready, apply, status):
    request_data.update(ready_ms=ready, apply_ms=apply)
    result = component.assess(request_data)
    assert result["status"] == status
    if apply >= 4200 and "simulated_output" in result:
        assert not result["simulated_output"]["credited"]


@pytest.mark.parametrize(
    "mutation",
    [
        "schema",
        "version",
        "frame",
        "delay",
        "authority",
        "physical",
        "bool_time",
        "new_field",
        "history",
        "sensors",
        "queued",
        "future_packet",
    ],
)
def test_incompatible_inputs_never_produce_positive_result(component, request_data, mutation):
    req = request_data
    if mutation == "schema":
        req["contract"]["schema"] = "old"
    elif mutation == "version":
        req["contract"]["component_version"] = "2.0.0"
    elif mutation == "frame":
        req["contract"]["model"]["frame"] = "inertial"
    elif mutation == "delay":
        req["contract"]["model"]["application_window_ms"] = [700, 720]
    elif mutation == "authority":
        req["contract"]["model"]["authority_mps2"] = "1"
    elif mutation == "physical":
        req["contract"]["model"]["physical_io"] = True
    elif mutation == "bool_time":
        req["ready_ms"] = True
    elif mutation == "new_field":
        req["certificate"] = {"valid": True}
    elif mutation == "history":
        req["current_input"]["history"][0]["action"] = ["0", "1/50"]
    elif mutation == "sensors":
        req["current_input"]["sensors"]["range_error_m"] = "1"
    elif mutation == "queued":
        req["current_input"]["queued_action"] = ["0", "1/50"]
    else:
        from iaa.types import ObservationPacket

        req["current_input"]["packets"] = [
            primitive(ObservationPacket("future", 0, "range", 45, 250, 900))
        ]
    assert component.assess(req)["status"] == "unsupported_input"


def test_covariance_or_external_certificate_not_credited(component, request_data):
    request_data["current_input"]["initial"] = {"covariance": [[0.01]], "point": [0, -45, 0, 0]}
    assert component.assess(request_data)["status"] == "unsupported_input"


def test_contract_and_input_are_not_shared_mutable_state(component, request_data):
    original = component.contract()
    other = component.contract()
    other["model"]["application_window_ms"][1] = 9999
    assert component.contract() == original
    before = deepcopy(request_data)
    result = component.assess(request_data)
    result["checked"]["binding"]["expires_ms"] = 9999
    assert request_data == before
    assert component.assess(before)["checked"]["binding"]["expires_ms"] == 4200


def test_record_recomputes_semantics_even_after_attacker_rehashes(component, request_data):
    receipt = component.record(request_data)
    assert component.replay(receipt)
    receipt["result"]["checked"]["binding"]["expires_ms"] = 9999
    receipt["sha256"] = identity({k: v for k, v in receipt.items() if k != "sha256"})
    assert not component.replay(receipt)


def test_estimator_result_has_no_negative_witness_authority(component, request_data):
    out = component.estimate_snapshot(request_data["current_input"])
    assert out["at_ms"] == 650 and out["outer_set_only"]
    assert not out["attainable_negative_witness"] and not out["physical_calibration"]


def test_public_consumer_uses_no_internal_implementation_imports():
    root = Path(__file__).resolve().parents[1] / "sa06/examples"
    for p in root.glob("*.py"):
        names = [
            n.module or ""
            for n in ast.walk(ast.parse(p.read_text()))
            if isinstance(n, ast.ImportFrom)
        ]
        assert not any("_vendor" in n or n.startswith(("iaa", "sa0")) for n in names)


def test_cli_rejects_nonfinite_or_duplicate_json(component, tmp_path):
    from kri_assurance_eval.cli import read

    p = tmp_path / "bad.json"
    for data in ('{"a":NaN}', '{"a":1,"a":2}', '"' + "x" * 300000 + '"'):
        p.write_text(data)
        with pytest.raises(ValueError):
            read(p)


def test_namespaced_modules_do_not_export_original_top_level_names(component):
    for name, module in sys.modules.copy().items():
        if name.startswith("kri_assurance_eval._vendor") and getattr(module, "__file__", None):
            assert "_vendor" in module.__file__


def test_isolated_consumer_process(component, tmp_path):
    staged_src = Path(component.__file__).parents[1]
    example = staged_src.parent / "examples/controller_adapter.py"
    env = {"PATH": "/usr/bin:/bin", "PYTHONPATH": str(staged_src)}
    p = subprocess.run(
        [sys.executable, str(example)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert p.returncode == 0, p.stderr
    result = json.loads(p.stdout)
    assert result["internal_integration"] and not result["external_replication"]


def test_public_packet_builder_and_conditioned_estimate(component, request_data):
    p = component.observation_packet("r", 1, "range", 45.0, 250, 290)
    request_data["current_input"]["packets"] = [p]
    out = component.estimate_snapshot(request_data["current_input"])
    assert out["status"] == "updated"
    assert out["uncertainty"]["diagnostics"]["retained_packets"] == 1
    assert component.assess(request_data)["status"] == "supported_prefix"
    with pytest.raises(ValueError):
        component.observation_packet("r", 1, "unknown", 1, 250, 290)


def test_existing_received_observation_cannot_be_changed(component, request_data):
    p = component.observation_packet("r", 0, "range", 45.0, 0, 40)
    request_data["initial_input"]["packets"] = [p]
    request_data["current_input"]["packets"] = [deepcopy(p)]
    assert component.assess(request_data)["status"] == "supported_prefix"
    request_data["current_input"]["packets"][0]["value"] = 44.9
    assert component.assess(request_data)["status"] == "unsupported_input"
