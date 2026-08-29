import inspect

import numpy as np

from kri_space_autonomy.experiment_002.config import load_config
from kri_space_autonomy.experiment_002.dynamics import TruthState, propagate_exact
from kri_space_autonomy.experiment_002.evaluator import RecoveryCorridor
from kri_space_autonomy.experiment_002.monitor import RuntimeGate
from kri_space_autonomy.experiment_002.policy import (
    FrozenPolicy,
    ReferenceController,
    SensorObservation,
)
from kri_space_autonomy.experiment_002.runner import _sensor_observation, run_block
from kri_space_autonomy.experiment_002.seeds import materialize_exogenous, materialize_scenario


def config():
    return load_config("experiments/002/config.json")


def policy():
    return FrozenPolicy(np.array([0.0, -1.0, -2.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]), config())


def corridor():
    return RecoveryCorridor(2.0, 130.0, 0.8, 0.1, "test", "test", "test")


def test_policy_and_gate_interfaces_have_no_truth_state():
    gate_signature = inspect.signature(RuntimeGate.gate)
    assert "TruthState" not in str(gate_signature)
    assert "TruthState" not in inspect.getsource(RuntimeGate)
    observation = SensorObservation(0.0, 10.0, -0.1, 0.9, 1.0)
    frozen = policy()
    decision = frozen.decide(observation)
    gate = RuntimeGate(config(), ReferenceController(config()), frozen.model_identity)
    assert (
        gate.gate(observation, decision).proposed_acceleration_mps2
        == decision.commanded_acceleration_mps2
    )


def test_protected_arms_have_identical_proposals_for_identical_primary_input():
    observation = SensorObservation(10.0, 20.0, -0.2, 0.8, 1.0)
    frozen = policy()
    ps_proposal = frozen.decide(observation)
    pd_proposal = frozen.decide(observation)
    assert ps_proposal == pd_proposal


def test_shared_exogenous_inputs_produce_arm_specific_truth():
    cfg = config()
    initial = TruthState(0.0, 20.0, -0.2, 0.9, 0.0)
    positive = propagate_exact(initial, 0.05, 1.0, 0.001, 1.0, cfg).state
    negative = propagate_exact(initial, -0.05, 1.0, 0.001, 1.0, cfg).state
    assert positive.range_m != negative.range_m
    assert positive.relative_velocity_mps != negative.relative_velocity_mps


def test_ps_copies_primary_while_pd_uses_independent_equal_spec_stream():
    cfg = config()
    spec = materialize_scenario(cfg, "P0_nominal", 0)
    streams, _ = materialize_exogenous(cfg, "P0_nominal", 0)
    history = [
        TruthState(
            0.0,
            spec.initial_range_m,
            spec.initial_velocity_mps,
            spec.initial_propellant,
            0.0,
        )
    ]
    primary = _sensor_observation("primary", 0.0, 0, history, streams, spec, cfg)
    monitor = _sensor_observation("monitor", 0.0, 0, history, streams, spec, cfg)
    ps_monitor = primary
    assert ps_monitor == primary
    assert (primary.range_m, primary.relative_velocity_mps) != (
        monitor.range_m,
        monitor.relative_velocity_mps,
    )


def test_four_arm_block_has_expected_cells_and_arm_specific_results():
    cfg = config()
    rows = run_block(cfg, "P0_nominal", 0, policy(), corridor(), "test-config")
    assert {row.arm for row in rows} == {"R", "D", "PS", "PD"}
    assert {row.run_order for row in rows} == {1, 2, 3, 4}
    assert all(row.elapsed_time_s == 600.0 or row.collision for row in rows)
    assert len({(row.minimum_range_m, row.propellant_used_fraction) for row in rows}) > 1
