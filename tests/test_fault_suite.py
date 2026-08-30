from __future__ import annotations

import importlib
import json
from copy import deepcopy
from dataclasses import fields
from pathlib import Path

import pytest

from kri_space_autonomy.controller_adapter import ControllerObservation
from kri_space_autonomy.fault_suite import (
    ActivationWindow,
    ActuatorEffectivenessFault,
    DeterministicFaultPipeline,
    FaultApplicationError,
    FaultCase,
    FaultSpecError,
    FaultSuiteLoadError,
    NavigationDropoutFault,
    ObservedRangeBiasFault,
    UnsupportedFaultError,
    fault_suite_from_dict,
    load_fault_suite,
    loads_fault_suite,
    replay_fault_suite,
    run_fault_suite,
    validate_fault_suite,
)
from kri_space_autonomy.fault_suite.cli import main
from kri_space_autonomy.types import Action, Observation

EXAMPLE_CONTROLLER = "kri_space_autonomy.examples.proportional_controller:controller"
EXAMPLE_SUITE = Path("fault-suites/example-rpo.json")


def _suite_dict() -> dict[str, object]:
    return {
        "schema_version": "kri-fault-suite/1.0",
        "suite_id": "test-suite",
        "description": "Test suite.",
        "runtime_profile": "simplified-rpo-v1",
        "initial_state": {
            "range": {"value": 100.0, "unit": "m"},
            "relative_velocity": {"value": -0.15, "unit": "m/s"},
            "propellant_fraction": {"value": 1.0, "unit": "ratio"},
        },
        "cases": [
            {"id": "nominal", "description": "Nominal.", "faults": []},
            {
                "id": "combined",
                "description": "Combined.",
                "faults": [
                    {
                        "id": "bias",
                        "type": "observed_range_bias",
                        "activation": {"start_step": 2, "end_step": 4},
                        "bias": {"value": 10.0, "unit": "m"},
                        "sensor_quality": {"value": 0.8, "unit": "ratio"},
                    },
                    {
                        "id": "dropout",
                        "type": "navigation_dropout",
                        "activation": {"start_step": 3, "end_step": 3},
                    },
                    {
                        "id": "degradation",
                        "type": "actuator_effectiveness",
                        "activation": {"start_step": 2, "end_step": 4},
                        "effectiveness": {"value": 0.5, "unit": "ratio"},
                    },
                ],
            },
        ],
    }


def _observation(step: int) -> Observation:
    return Observation(
        step=step,
        range_m=20.0,
        relative_velocity_mps=-0.1,
        propellant=0.9,
        sensor_quality=1.0,
    )


def _write_recording_controller(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> str:
    name = "fault_suite_recording_controller"
    source = """
from dataclasses import fields
from kri_space_autonomy.controller_adapter import ControllerCommand, ControllerMetadata

class RecordingController:
    metadata = ControllerMetadata(controller_id="test.recording", controller_version="1.0")

    def reset(self, context):
        self.argument_counts = []
        self.observation_fields = []

    def command(self, *arguments):
        self.argument_counts.append(len(arguments))
        observation = arguments[0]
        self.observation_fields.append(tuple(field.name for field in fields(observation)))
        return ControllerCommand(0.05)

controller = RecordingController()
"""
    (tmp_path / f"{name}.py").write_text(source, encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    importlib.invalidate_caches()
    return f"{name}:controller"


def test_example_suite_validates_with_stable_case_and_suite_identities():
    first = validate_fault_suite(EXAMPLE_SUITE)
    second = validate_fault_suite(EXAMPLE_SUITE)
    assert first == second
    assert first["passed"] is True
    assert first["case_count"] == 5
    assert len(first["suite_sha256"]) == 64
    assert all(len(case["case_sha256"]) == 64 for case in first["cases"])

    compact = json.dumps(json.loads(EXAMPLE_SUITE.read_text(encoding="utf-8")))
    assert loads_fault_suite(compact).sha256 == load_fault_suite(EXAMPLE_SUITE).sha256


def test_manifest_order_is_composition_order_and_part_of_identity():
    original = _suite_dict()
    first = fault_suite_from_dict(original)
    reordered = deepcopy(original)
    faults = reordered["cases"][1]["faults"]
    faults[0], faults[1] = faults[1], faults[0]
    second = fault_suite_from_dict(reordered)
    assert first.cases[1].sha256 != second.cases[1].sha256
    assert first.sha256 != second.sha256
    assert [fault.fault_id for fault in first.cases[1].faults] == [
        "bias",
        "dropout",
        "degradation",
    ]


def test_observed_range_bias_has_inclusive_activation_boundaries():
    pipeline = DeterministicFaultPipeline(
        FaultCase(
            "bias",
            "Bias.",
            (
                ObservedRangeBiasFault(
                    "range-bias", ActivationWindow(2, 4), 7.5, 0.75
                ),
            ),
        )
    )
    assert pipeline.apply_observation(_observation(1)) == _observation(1)
    assert pipeline.apply_observation(_observation(2)).range_m == 27.5
    assert pipeline.apply_observation(_observation(4)).sensor_quality == 0.75
    assert pipeline.apply_observation(_observation(5)) == _observation(5)


def test_navigation_dropout_sets_only_public_navigation_fields_missing():
    pipeline = DeterministicFaultPipeline(
        FaultCase(
            "dropout",
            "Dropout.",
            (NavigationDropoutFault("nav", ActivationWindow(2, 4)),),
        )
    )
    before = _observation(1)
    assert pipeline.apply_observation(before) == before
    for step in (2, 4):
        after = pipeline.apply_observation(_observation(step))
        assert after.range_m is None
        assert after.relative_velocity_mps is None
        assert after.propellant == 0.9
        assert after.sensor_quality == 0.0
    assert pipeline.apply_observation(_observation(5)) == _observation(5)


def test_actuator_effectiveness_applies_after_command_at_inclusive_boundaries():
    pipeline = DeterministicFaultPipeline(
        FaultCase(
            "actuator",
            "Actuator.",
            (
                ActuatorEffectivenessFault(
                    "effectiveness", ActivationWindow(2, 4), 0.4
                ),
            ),
        )
    )
    command = Action(-0.05)
    assert pipeline.apply_action(1, command) == command
    assert pipeline.apply_action(2, command).acceleration_mps2 == pytest.approx(-0.02)
    assert pipeline.apply_action(4, command).acceleration_mps2 == pytest.approx(-0.02)
    assert pipeline.apply_action(5, command) == command


def test_compatible_faults_compose_deterministically_in_array_order():
    pipeline = DeterministicFaultPipeline(
        FaultCase(
            "composed",
            "Composed.",
            (
                ObservedRangeBiasFault("bias-a", ActivationWindow(0, 0), 10.0, 0.9),
                ObservedRangeBiasFault("bias-b", ActivationWindow(0, 0), -3.0, 0.7),
                ActuatorEffectivenessFault("actuator-a", ActivationWindow(0, 0), 0.5),
                ActuatorEffectivenessFault("actuator-b", ActivationWindow(0, 0), 0.4),
            ),
        )
    )
    observed = pipeline.apply_observation(_observation(0))
    executed = pipeline.apply_action(0, Action(0.05))
    assert observed.range_m == 27.0
    assert observed.sensor_quality == 0.7
    assert executed.acceleration_mps2 == pytest.approx(0.01)
    assert pipeline.active_fault_ids(0) == (
        "bias-a",
        "bias-b",
        "actuator-a",
        "actuator-b",
    )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda data: data.update({"extra": 1}), "unknown keys"),
        (lambda data: data.update({"schema_version": "2"}), "schema_version"),
        (
            lambda data: data["initial_state"]["range"].update({"unit": "km"}),
            "unit must be 'm'",
        ),
        (
            lambda data: data["cases"][1]["faults"][0]["activation"].update(
                {"start_step": True}
            ),
            "start_step",
        ),
        (
            lambda data: data["cases"][1]["faults"][0]["activation"].update(
                {"start_step": 5, "end_step": 4}
            ),
            "greater than or equal",
        ),
        (
            lambda data: data["cases"][1]["faults"][0]["activation"].update(
                {"end_step": 500}
            ),
            "below 500",
        ),
        (
            lambda data: data["cases"][1]["faults"][2]["effectiveness"].update(
                {"value": 1.1}
            ),
            r"in \[0, 1\]",
        ),
        (
            lambda data: data["cases"][1]["faults"][0]["bias"].update(
                {"value": float("inf")}
            ),
            "must be finite",
        ),
    ],
)
def test_invalid_specs_fail_closed_with_typed_errors(mutation, message: str):
    data = _suite_dict()
    mutation(data)
    with pytest.raises(FaultSpecError, match=message):
        fault_suite_from_dict(data)


def test_programmatic_mapping_keys_must_be_strings():
    data = _suite_dict()
    data[1] = "invalid"
    with pytest.raises(FaultSpecError, match="keys must be strings"):
        fault_suite_from_dict(data)


def test_duplicate_json_keys_and_nonfinite_constants_are_rejected():
    with pytest.raises(FaultSuiteLoadError, match="duplicate JSON key"):
        loads_fault_suite('{"schema_version":"a","schema_version":"b"}')
    with pytest.raises(FaultSuiteLoadError, match="non-finite JSON constant"):
        loads_fault_suite('{"value":NaN}')
    with pytest.raises(FaultSuiteLoadError, match="non-finite JSON constant"):
        loads_fault_suite('{"value":Infinity}')


def test_duplicate_ids_and_unsupported_internal_faults_are_rejected():
    duplicate = _suite_dict()
    duplicate["cases"].append(deepcopy(duplicate["cases"][0]))
    with pytest.raises(FaultSpecError, match="duplicate case id"):
        fault_suite_from_dict(duplicate)

    duplicate_fault = _suite_dict()
    repeated = deepcopy(duplicate_fault["cases"][1]["faults"][0])
    duplicate_fault["cases"][1]["faults"].append(repeated)
    with pytest.raises(FaultSpecError, match="duplicate fault id"):
        fault_suite_from_dict(duplicate_fault)

    unknown = _suite_dict()
    unknown["cases"][1]["faults"][0]["type"] = "not_a_fault"
    with pytest.raises(UnsupportedFaultError, match="unsupported"):
        fault_suite_from_dict(unknown)

    unsupported = _suite_dict()
    unsupported_fault = unsupported["cases"][1]["faults"][0]
    unsupported_fault.clear()
    unsupported_fault.update(
        {
            "id": "internal",
            "type": "controller_internal",
            "activation": {"start_step": 1, "end_step": 2},
        }
    )
    with pytest.raises(UnsupportedFaultError, match="internal corruption"):
        fault_suite_from_dict(unsupported)


def test_programmatic_specs_reject_nonfinite_values_before_application():
    with pytest.raises(FaultSpecError, match="bias_m must be finite"):
        ObservedRangeBiasFault(
            "bad-bias", ActivationWindow(0, 1), float("nan"), 0.8
        )
    with pytest.raises(FaultSpecError, match="effectiveness must be in"):
        ActuatorEffectivenessFault("bad-actuator", ActivationWindow(0, 1), -0.1)


def test_fault_application_rejects_malformed_runtime_inputs():
    pipeline = DeterministicFaultPipeline(FaultCase("nominal", "Nominal.", ()))
    with pytest.raises(FaultApplicationError, match="Observation"):
        pipeline.apply_observation(object())
    with pytest.raises(FaultApplicationError, match="range_m"):
        pipeline.apply_observation(
            Observation(0, float("nan"), 0.0, 1.0, 1.0)
        )
    with pytest.raises(FaultApplicationError, match="non-negative integer"):
        pipeline.apply_action(-1, Action(0.0))
    with pytest.raises(FaultApplicationError, match="finite real scalar"):
        pipeline.apply_action(0, Action(float("nan")))


def test_controller_receives_one_unchanged_public_observation_argument(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    spec = _write_recording_controller(tmp_path, monkeypatch)
    result = run_fault_suite(spec, EXAMPLE_SUITE)
    assert len(result.cases) == 5
    module = importlib.import_module("fault_suite_recording_controller")
    expected = tuple(field.name for field in fields(ControllerObservation))
    assert module.controller.argument_counts
    assert set(module.controller.argument_counts) == {1}
    assert set(module.controller.observation_fields) == {expected}
    assert "achieved_acceleration_mps2" not in expected
    assert "active_fault_ids" not in expected


def test_example_suite_runs_and_replays_exactly_with_actuator_application():
    first = run_fault_suite(EXAMPLE_CONTROLLER, EXAMPLE_SUITE)
    second = run_fault_suite(EXAMPLE_CONTROLLER, EXAMPLE_SUITE)
    assert first == second
    assert first.to_dict() == second.to_dict()
    assert len(first.result_sha256) == 64
    rendered = json.dumps(first.to_dict(), sort_keys=True)
    assert str(EXAMPLE_SUITE) not in rendered
    assert "initial_state" not in rendered
    cases = {case.case_id: case for case in first.cases}
    assert cases["navigation-dropout"].missing_observation_steps == 16
    assert cases["actuator-degradation"].actuator_modified_steps > 0
    assert cases["dropout-plus-degradation"].missing_observation_steps == 16
    assert cases["dropout-plus-degradation"].actuator_modified_steps > 0
    replay = replay_fault_suite(EXAMPLE_CONTROLLER, EXAMPLE_SUITE)
    assert replay["passed"] is True
    assert replay["replay_match"] is True
    assert replay["result"] == first.to_dict()


def test_cli_validate_run_and_replay_suite(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
):
    assert main(["validate", str(EXAMPLE_SUITE)]) == 0
    assert json.loads(capsys.readouterr().out)["case_count"] == 5

    output = tmp_path / "suite-result.json"
    assert main(
        [
            "run-suite",
            EXAMPLE_CONTROLLER,
            str(EXAMPLE_SUITE),
            "--output",
            str(output),
        ]
    ) == 0
    run_result = json.loads(capsys.readouterr().out)
    assert run_result["suite_id"] == "example-rpo-faults"
    assert json.loads(output.read_text(encoding="utf-8")) == run_result

    assert main(["replay-suite", EXAMPLE_CONTROLLER, str(EXAMPLE_SUITE)]) == 0
    assert json.loads(capsys.readouterr().out)["replay_match"] is True
