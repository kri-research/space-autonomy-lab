import numpy as np

from kri_space_autonomy.experiment_002.policy import FrozenPolicy
from kri_space_autonomy.experiment_002.runner import load_recovery_corridor
from kri_space_autonomy.experiment_002.seeds import ExogenousStreams
from kri_space_autonomy.experiment_002_confirmatory.config import (
    load_confirmatory_config,
)
from kri_space_autonomy.experiment_002_confirmatory.runner import run_scenario_block
from kri_space_autonomy.experiment_002_confirmatory.seeds import (
    materialize_nonreserved_test_scenario,
)


def test_full_four_arm_combined_fault_fixture_runs_with_corrected_production():
    study, production = load_confirmatory_config(
        "experiments/002-confirmatory/config.json"
    )
    scenario = materialize_nonreserved_test_scenario(
        study,
        production,
        "F7_combined_primary_dropout_actuator_degradation",
        3,
        partition_code=916,
    )
    n = production.n_exogenous_steps
    zeros = np.zeros(n + 1, dtype=np.float64)
    streams = ExogenousStreams(
        process_acceleration_mps2=np.zeros(n, dtype=np.float64),
        primary_range_noise_m=zeros.copy(),
        primary_velocity_noise_mps=zeros.copy(),
        primary_latency_s=zeros.copy(),
        monitor_range_noise_m=zeros.copy(),
        monitor_velocity_noise_mps=zeros.copy(),
        monitor_latency_s=zeros.copy(),
    )
    policy = FrozenPolicy.load(
        "artifacts/experiment-002/policy-primary.npz",
        "artifacts/experiment-002/policy-primary.manifest.json",
        production,
    )
    corridor = load_recovery_corridor("experiments/002/recovery-corridor.json")
    rows = run_scenario_block(
        scenario,
        streams,
        policy,
        corridor,
        study,
        production,
        "study-config-test-hash",
        "production-config-test-hash",
        "freeze-test-id",
    )
    assert len(rows) == 4
    assert {row.arm for row in rows} == set(study.arms)
    assert {row.stratum_id for row in rows} == {
        "F7_combined_primary_dropout_actuator_degradation"
    }
    assert all(row.study_phase == "confirmatory" for row in rows)
    assert all(row.controller_command_period_s == 1.0 for row in rows)
    assert all(row.freeze_id == "freeze-test-id" for row in rows)
