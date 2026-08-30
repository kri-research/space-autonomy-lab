from dataclasses import replace

import numpy as np

from kri_space_autonomy.experiment_002.dynamics import TruthState
from kri_space_autonomy.experiment_002.policy import FrozenPolicy
from kri_space_autonomy.experiment_002d.config import load_combined_information_config
from kri_space_autonomy.experiment_002d.runner import (
    _actuator_effectiveness,
    _sensor_observation,
    _split_interval,
    run_information_arm,
)
from kri_space_autonomy.experiment_002d.seeds import (
    materialize_exogenous_002d,
    materialize_scenario_002d,
)


def test_combined_fault_affects_primary_sensor_and_actuator_independently():
    study, production = load_combined_information_config("experiments/002d/config.json")
    short = replace(production, horizon_s=2.0)
    base = materialize_scenario_002d(study, short, 0)
    spec = replace(
        base,
        dropout_onset_s=0.0,
        dropout_end_s=1.0,
        actuator_onset_gap_s=0.5,
        actuator_onset_s=0.5,
        actuator_end_s=1.5,
        actuator_effectiveness=0.4,
    )
    streams, _ = materialize_exogenous_002d(study, short, 0)
    history = [
        TruthState(
            0.0,
            spec.initial_range_m,
            spec.initial_velocity_mps,
            spec.initial_propellant,
            0.0,
        )
    ]
    primary = _sensor_observation("primary", 0.0, 0, history, streams, spec, short)
    monitor = _sensor_observation("monitor", 0.0, 0, history, streams, spec, short)
    assert primary.range_m is None and primary.relative_velocity_mps is None
    assert monitor.range_m is not None and monitor.relative_velocity_mps is not None
    assert _actuator_effectiveness(spec, 0.25) == 1.0
    assert _actuator_effectiveness(spec, 1.0) == 0.4
    assert _actuator_effectiveness(spec, 1.75) == 1.0
    assert _split_interval(0.25, 1.75, spec) == [
        (0.25, 0.5),
        (0.5, 1.5),
        (1.5, 1.75),
    ]


def test_short_paired_runs_use_episode_level_rows_and_independent_truth_evaluator():
    study, production = load_combined_information_config("experiments/002d/config.json")
    short = replace(production, horizon_s=2.0, goal_dwell_s=1.0)
    spec = materialize_scenario_002d(study, short, 1)
    streams, _ = materialize_exogenous_002d(study, short, 1)
    policy = FrozenPolicy(
        np.array([0.0, -1.0, -2.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]),
        short,
    )
    rows = [
        run_information_arm(
            spec,
            streams,
            arm,
            order,
            policy,
            short,
            "study-config",
            "production-config",
        )
        for order, arm in enumerate(("D", "PD"), start=1)
    ]
    assert len(rows) == 2
    assert {row.arm for row in rows} == {"D", "PD"}
    assert all(row.root_seed_id == spec.root_seed_id for row in rows)
    assert all(row.elapsed_time_s == 2.0 or row.collision for row in rows)
    assert all(isinstance(row.analysis_hazard, bool) for row in rows)
    assert all(row.exogenous_hashes == spec.stream_hashes for row in rows)
