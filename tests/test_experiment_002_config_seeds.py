import json
from dataclasses import replace

import numpy as np

from kri_space_autonomy.experiment_002.config import MIXED_STRATA, PILOT_STRATA, load_config
from kri_space_autonomy.experiment_002.seeds import (
    materialize_exogenous,
    materialize_scenario,
    validate_pilot_manifest,
    write_seed_manifests,
)


def config():
    return load_config("experiments/002/config.json")


def test_canonical_pilot_size_and_fixed_mixtures(tmp_path):
    cfg = config()
    assert cfg.seeds_per_stratum == 400
    assert cfg.planned_blocks == 2400
    assert cfg.planned_episodes == 9600
    write_seed_manifests(cfg, tmp_path)
    validation = validate_pilot_manifest(cfg, tmp_path / "pilot.jsonl")
    assert validation["valid"]
    assert validation["stratum_counts"] == {stratum: 400 for stratum in PILOT_STRATA}
    for stratum in MIXED_STRATA:
        assert validation["subtype_counts"][stratum] == {
            "range_bias": 200,
            "dropout": 200,
        }


def test_seed_replay_and_named_stream_independence():
    cfg = config()
    first = materialize_scenario(cfg, "P1_primary_navigation", 7)
    replay = materialize_scenario(cfg, "P1_primary_navigation", 7)
    other = materialize_scenario(cfg, "P1_primary_navigation", 8)
    assert first == replay
    assert first.scenario_hash != other.scenario_hash
    streams_a, hashes_a = materialize_exogenous(cfg, "P1_primary_navigation", 7)
    streams_b, hashes_b = materialize_exogenous(cfg, "P1_primary_navigation", 7)
    assert hashes_a == hashes_b
    assert np.array_equal(streams_a.process_acceleration_mps2, streams_b.process_acceleration_mps2)
    assert hashes_a["primary_sensor"] != hashes_a["monitor_sensor"]


def test_invalid_seed_count_is_rejected():
    cfg = replace(config(), seeds_per_stratum=399)
    try:
        cfg.validate()
    except ValueError as error:
        assert "400" in str(error)
    else:
        raise AssertionError("noncanonical seed count was accepted")


def test_future_confirmatory_partition_is_reserved_not_executed(tmp_path):
    cfg = config()
    write_seed_manifests(cfg, tmp_path)
    reserved = json.loads((tmp_path / "future_confirmatory_reserved.json").read_text())
    assert reserved["status"] == "reserved_not_materialized_or_executed"
