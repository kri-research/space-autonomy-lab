import hashlib
import json

from kri_space_autonomy.experiment_002.policy import FrozenPolicy
from kri_space_autonomy.experiment_003.config import load_config
from kri_space_autonomy.experiment_003.runner import run_arm
from kri_space_autonomy.experiment_003.seeds import materialize_test_scenario


def setup():
    study, production = load_config("experiments/003/config.json")
    policy = FrozenPolicy.load(
        "artifacts/experiment-002/policy-primary.npz",
        "artifacts/experiment-002/policy-primary.manifest.json",
        production,
    )
    return study, production, policy


def trace_hash(trace):
    payload = json.dumps(trace, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode()).hexdigest()


def test_non_outcome_closed_loop_fixture_replays_exactly():
    study, production, policy = setup()
    scenario, streams = materialize_test_scenario(
        study, production, "E0_nominal", 0
    )
    first, first_trace = run_arm(
        study,
        production,
        scenario,
        streams,
        "D",
        1,
        policy,
        "fixture-config",
        collect_trace=True,
    )
    replay, replay_trace = run_arm(
        study,
        production,
        scenario,
        streams,
        "D",
        1,
        policy,
        "fixture-config",
        collect_trace=True,
    )
    assert first == replay
    assert first_trace is not None and replay_trace is not None
    assert trace_hash(first_trace) == trace_hash(replay_trace)
    assert first.root_seed_id.startswith("fixture003:")
    assert first.elapsed_time_s == 600.0 or first.collision


def test_dropout_fixture_uses_prediction_only_updates_without_truth_reset():
    study, production, policy = setup()
    scenario, streams = materialize_test_scenario(
        study, production, "E2_primary_dropout", 1
    )
    result, _ = run_arm(
        study,
        production,
        scenario,
        streams,
        "PD",
        1,
        policy,
        "fixture-config",
    )
    assert result.primary_accepted_updates < result.monitor_accepted_updates
    assert result.primary_estimator_diverged is False
    assert result.monitor_estimator_diverged is False
