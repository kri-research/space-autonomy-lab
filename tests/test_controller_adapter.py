from __future__ import annotations

import hashlib
import importlib
import json
from dataclasses import fields, replace
from pathlib import Path

import pytest

from kri_space_autonomy.controller_adapter import (
    ControllerContext,
    ControllerContractError,
    ControllerExecutionError,
    ControllerLoadError,
    ControllerObservation,
    ObservationStatus,
    UnsupportedScenarioError,
    load_controller,
    replay_external_controller,
    run_external_controller,
    run_loaded_controller,
    validate_controller,
)
from kri_space_autonomy.controller_adapter.cli import main
from kri_space_autonomy.environment import EnvironmentConfig
from kri_space_autonomy.scenario import load_scenario

EXAMPLE = "kri_space_autonomy.examples.proportional_controller:controller"


def _write_plugin(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    *,
    command_body: str = "return ControllerCommand(0.0)",
    reset_body: str = "return None",
    metadata: str = (
        "ControllerMetadata(controller_id='test.controller', controller_version='1.0')"
    ),
) -> str:
    source = f"""
from kri_space_autonomy.controller_adapter import (
    ControllerCommand,
    ControllerMetadata,
)

class TestController:
    metadata = {metadata}

    def reset(self, context):
        {reset_body}

    def command(self, observation):
        {command_body}

controller = TestController()
"""
    (tmp_path / f"{name}.py").write_text(source, encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    importlib.invalidate_caches()
    return f"{name}:controller"


def test_public_observation_surface_contains_only_controller_observables():
    assert tuple(field.name for field in fields(ControllerObservation)) == (
        "step",
        "time_s",
        "range_m",
        "relative_velocity_mps",
        "propellant_fraction",
        "sensor_quality",
    )
    assert tuple(field.name for field in fields(ControllerContext)) == (
        "command_period_s",
        "minimum_acceleration_mps2",
        "maximum_acceleration_mps2",
        "acceleration_unit",
        "positive_acceleration",
    )
    observation = ControllerObservation(0, 0.0, None, None, 0.8, 0.0)
    assert observation.status is ObservationStatus.MISSING
    assert observation.missing_fields == ("range_m", "relative_velocity_mps")
    assert not hasattr(observation, "state")
    assert not hasattr(observation, "achieved_acceleration_mps2")


def test_example_validates_and_has_stable_source_identity():
    first = validate_controller(EXAMPLE)
    second = validate_controller(EXAMPLE)
    assert first == second
    assert first["passed"] is True
    assert first["probe_statuses"] == ["nominal", "degraded", "missing"]
    assert first["reset_replay_match"] is True
    digest = first["controller"]["plugin_module_sha256"]
    assert isinstance(digest, str) and len(digest) == 64


def test_example_runs_end_to_end_and_replays_exactly():
    first = run_external_controller(EXAMPLE, "scenarios/nominal.json")
    second = run_external_controller(EXAMPLE, "scenarios/nominal.json")
    assert first == second
    assert first.commands == first.steps
    assert len(first.command_trace_sha256) == 64
    replay = replay_external_controller(EXAMPLE, "scenarios/nominal.json")
    assert replay["passed"] is True
    assert replay["result"] == first.to_dict()


def test_missing_observations_reach_controller_without_truth_fill():
    result = run_external_controller(EXAMPLE, "scenarios/sensor-dropout.json")
    assert result.missing_observation_steps > 0
    assert result.degraded_observation_steps >= result.missing_observation_steps


def test_runner_passes_only_public_observation_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    name = "recording_controller"
    spec = _write_plugin(
        tmp_path,
        monkeypatch,
        name,
        command_body=(
            "self.seen.append(tuple(field.name for field in fields(observation))); "
            "return ControllerCommand(0.05)"
        ),
        reset_body="self.seen = []",
    )
    path = tmp_path / f"{name}.py"
    source = path.read_text(encoding="utf-8").replace(
        "from kri_space_autonomy.controller_adapter import (",
        "from dataclasses import fields\nfrom kri_space_autonomy.controller_adapter import (",
    )
    path.write_text(source, encoding="utf-8")
    importlib.invalidate_caches()

    adapter = load_controller(spec)
    scenario = load_scenario("scenarios/nominal.json")
    run_loaded_controller(adapter, scenario)
    module = importlib.import_module(name)
    expected = tuple(field.name for field in fields(ControllerObservation))
    assert module.controller.seen
    assert set(module.controller.seen) == {expected}


def test_model_representation_fault_is_explicitly_out_of_scope():
    with pytest.raises(UnsupportedScenarioError, match="not part of the external controller"):
        run_external_controller(EXAMPLE, "scenarios/model-seu.json")


@pytest.mark.parametrize(
    "config",
    [
        replace(EnvironmentConfig(), max_steps=1.5),
        replace(EnvironmentConfig(), propellant_cost_per_mps2=-0.1),
        replace(EnvironmentConfig(), goal_min_range_m=1.0),
        replace(EnvironmentConfig(), propellant_reserve=float("nan")),
    ],
)
def test_malformed_environment_config_fails_closed(config: EnvironmentConfig):
    adapter = load_controller(EXAMPLE)
    scenario = load_scenario("scenarios/nominal.json")
    with pytest.raises(ControllerContractError, match="environment"):
        run_loaded_controller(adapter, scenario, config)


def test_command_requires_reset_and_contiguous_time_sequence():
    adapter = load_controller(EXAMPLE)
    observation = ControllerObservation(0, 0.0, 10.0, -0.1, 1.0, 1.0)
    with pytest.raises(ControllerContractError, match="reset"):
        adapter.command(observation)
    context = ControllerContext(1.0, -0.05, 0.05)
    adapter.reset(context)
    with pytest.raises(ControllerContractError, match="step must be 0"):
        adapter.command(ControllerObservation(1, 1.0, 10.0, -0.1, 1.0, 1.0))
    adapter.reset(context)
    adapter.command(observation)
    with pytest.raises(ControllerContractError, match="observation time"):
        adapter.command(
            ControllerObservation(1, 1.0000000005, 10.0, -0.1, 1.0, 1.0)
        )


@pytest.mark.parametrize(
    ("expression", "message"),
    [
        ("ControllerCommand(float('nan'))", "must be finite"),
        ("ControllerCommand(float('inf'))", "must be finite"),
        ("ControllerCommand(0.051)", "outside the declared episode bounds"),
        ("ControllerCommand('0.0')", "must be a real scalar"),
        (
            "ControllerCommand(0.0, acceleration_unit='km/s^2')",
            "acceleration_unit must be 'm/s\\^2'",
        ),
        ("[0.0]", "must return ControllerCommand"),
        ("{'thrust_newtons': 1.0}", "must return ControllerCommand"),
    ],
)
def test_invalid_outputs_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    expression: str,
    message: str,
):
    suffix = hashlib.sha256(expression.encode()).hexdigest()[:10]
    spec = _write_plugin(
        tmp_path,
        monkeypatch,
        f"invalid_output_{suffix}",
        command_body=f"return {expression}",
    )
    with pytest.raises(ControllerContractError, match=message):
        validate_controller(spec)


def test_controller_exception_is_wrapped_and_stops_lifecycle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    spec = _write_plugin(
        tmp_path,
        monkeypatch,
        "raising_controller",
        command_body="raise RuntimeError('command failed')",
    )
    adapter = load_controller(spec)
    adapter.reset(ControllerContext(1.0, -0.05, 0.05))
    observation = ControllerObservation(0, 0.0, 10.0, -0.1, 1.0, 1.0)
    with pytest.raises(ControllerExecutionError, match="RuntimeError"):
        adapter.command(observation)
    with pytest.raises(ControllerContractError, match="reset"):
        adapter.command(observation)


def test_reset_must_return_none(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    spec = _write_plugin(
        tmp_path,
        monkeypatch,
        "bad_reset_controller",
        reset_body="return 'ready'",
    )
    with pytest.raises(ControllerContractError, match="reset must return None"):
        validate_controller(spec)


def test_deterministic_claim_requires_reset_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    spec = _write_plugin(
        tmp_path,
        monkeypatch,
        "non_replaying_controller",
        reset_body="self.counter = getattr(self, 'counter', 0)",
        command_body="self.counter += 1; return ControllerCommand(self.counter * 0.001)",
    )
    with pytest.raises(ControllerContractError, match="reset replay"):
        validate_controller(spec)


def test_malformed_loader_inputs_fail_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    with pytest.raises(ControllerLoadError, match="module.path:attribute"):
        load_controller("not-a-spec")
    spec = _write_plugin(
        tmp_path,
        monkeypatch,
        "bad_metadata_controller",
        metadata="{'controller_id': 'wrong-shape'}",
    )
    with pytest.raises(ControllerContractError, match="metadata"):
        load_controller(spec)
    with pytest.raises(ControllerLoadError, match="was not found"):
        load_controller("bad_metadata_controller:missing")


def test_cli_validate_run_and_replay(capsys: pytest.CaptureFixture[str]):
    assert main(["validate", EXAMPLE]) == 0
    assert json.loads(capsys.readouterr().out)["passed"] is True
    assert main(["run", EXAMPLE, "scenarios/nominal.json"]) == 0
    assert json.loads(capsys.readouterr().out)["controller_id"] == "example.proportional"
    assert main(["replay", EXAMPLE, "scenarios/nominal.json"]) == 0
    assert json.loads(capsys.readouterr().out)["replay_match"] is True
