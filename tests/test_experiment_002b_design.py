import json
import math
from dataclasses import replace

from kri_space_autonomy.experiment_002.config import PILOT_STRATA
from kri_space_autonomy.experiment_002.policy import FrozenPolicy
from kri_space_autonomy.experiment_002b.analysis import one_sided_exact_upper
from kri_space_autonomy.experiment_002b.config import load_amendment_config
from kri_space_autonomy.experiment_002b.runner import run_pd_episode
from kri_space_autonomy.experiment_002b.seeds import (
    materialize_exogenous_002b,
    materialize_scenario_002b,
)


def test_prospective_sample_size_and_supported_period_are_frozen():
    amendment, production = load_amendment_config("experiments/002b/config.json")
    assert amendment.minimum_zero_event_n == 149
    assert amendment.operational_seeds_per_stratum == 150
    assert amendment.zero_event_upper_bound < 0.02
    assert math.isclose(
        amendment.zero_event_upper_bound,
        one_sided_exact_upper(0, 150, 0.95),
        abs_tol=1e-15,
    )
    assert amendment.operational_command_period_s == production.command_period_s == 1.0


def test_new_seed_domains_are_disjoint_and_mixed_strata_are_balanced():
    amendment, production = load_amendment_config("experiments/002b/config.json")
    assert min(
        amendment.operational_partition_code,
        amendment.rate_partition_code,
        amendment.replay_partition_code,
    ) > 19
    historical_ids = set()
    for path in __import__("pathlib").Path("experiments/002/seeds").glob("*.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            root_id = json.loads(line).get("root_seed_id")
            if root_id:
                historical_ids.add(root_id)
    generated = set()
    for partition, size in (("operational", 150), ("rate_decomposition", 12)):
        for stratum in PILOT_STRATA:
            subtypes = []
            for replicate in range(size):
                scenario = materialize_scenario_002b(
                    amendment, production, partition, stratum, replicate
                )
                assert scenario.root_seed_id not in historical_ids
                assert scenario.root_seed_id not in generated
                generated.add(scenario.root_seed_id)
                subtypes.append(scenario.fault_subtype)
            if stratum in {
                "P1_primary_navigation",
                "P2_monitor_only",
                "P3_shared_cause_navigation",
            }:
                assert subtypes.count("range_bias") == size // 2
                assert subtypes.count("dropout") == size // 2


def test_command_and_observation_periods_vary_independently():
    amendment, production = load_amendment_config("experiments/002b/config.json")
    short = replace(production, horizon_s=2.0)
    spec = materialize_scenario_002b(
        amendment, short, "rate_decomposition", "P0_nominal", 0
    )
    streams, _ = materialize_exogenous_002b(
        amendment, short, "rate_decomposition", "P0_nominal", 0
    )
    policy = FrozenPolicy.load(
        "artifacts/experiment-002/policy-primary.npz",
        "artifacts/experiment-002/policy-primary.manifest.json",
        short,
    )
    events = []
    result, _ = run_pd_episode(
        amendment,
        short,
        spec,
        streams,
        policy,
        command_period_s=0.25,
        observation_period_s=1.0,
        config_hash="test",
        study_component="test",
        event_sink=events.append,
    )
    assert result.command_decisions == 8
    assert result.primary_sensor_packets == 2
    assert result.monitor_sensor_packets == 2
    assert [event["primary_sample_time_s"] for event in events[:4]] == [0.0] * 4
    assert [event["primary_sample_time_s"] for event in events[4:]] == [1.0] * 4
    assert max(event["primary_packet_age_s"] for event in events) == 0.75
