import json
from dataclasses import replace
from pathlib import Path

from kri_space_autonomy.experiment_002d.analysis import (
    _planning_power,
    historical_nuisance,
    validate_information_cells,
)
from kri_space_autonomy.experiment_002d.config import (
    COMBINED_STRATUM,
    load_combined_information_config,
)


def test_historical_p1_is_split_into_confirmatory_f1_and_f2_nuisance():
    nuisance = historical_nuisance("results/experiment-002/episodes.jsonl")
    assert len(nuisance) == 7
    assert nuisance["F1_primary_range_bias"]["paired_blocks"] == 200
    assert nuisance["F2_primary_dropout"]["paired_blocks"] == 200
    assert nuisance["F3_monitor_channel_fault"]["paired_blocks"] == 400
    assert nuisance["F6_actuator_degradation"]["paired_blocks"] == 400


def test_information_cell_validation_counts_root_blocks_not_steps():
    study, _ = load_combined_information_config("experiments/002d/config.json")
    rows = []
    for replicate in range(study.information_seeds):
        for arm in study.arms:
            rows.append(
                {
                    "root_seed_id": f"root:{replicate}",
                    "arm": arm,
                    "stratum_id": COMBINED_STRATUM,
                    "fault_subtype": "primary_dropout_plus_actuator_degradation",
                }
            )
    result = validate_information_cells(rows, study)
    assert result["valid"]
    assert result["complete_blocks"] == 299
    assert result["episode_rows"] == 598


def test_eight_stratum_power_allows_q_equal_one_and_reports_marginal_endpoints():
    study, _ = load_combined_information_config("experiments/002d/config.json")
    small = replace(study, power_simulations=2000)
    base = historical_nuisance("results/experiment-002/episodes.jsonl")
    base[COMBINED_STRATUM] = {
        "direct_hazard_risk": 0.0,
        "direct_hazard_lower95": 0.0,
        "hazard_discordance": {"one_sided_95_upper": 1.0},
        "success_discordance": {"one_sided_95_upper": 1.0},
    }
    result = _planning_power(
        base,
        small,
        lambda values: float(values["direct_hazard_lower95"]),
        scenario_index=99,
    )
    assert "marginal endpoint power only" in result["method"]
    assert set(result["candidate_confirmatory_seeds_per_stratum"]) == {
        "1000",
        "1500",
        "2000",
    }
    for candidate in result["candidate_confirmatory_seeds_per_stratum"].values():
        assert 0.0 <= candidate["h1_marginal_power"] <= 1.0
        assert 0.0 <= candidate["h2_marginal_power"] <= 1.0


def test_stratum_map_source_hash_is_frozen():
    mapping = json.loads(
        Path("experiments/002d/confirmatory-stratum-map.json").read_text()
    )
    assert mapping["source_document_sha256"] == (
        "ffd1dba3195edd583797181702125cff4a81456502dba5c2a652ce1aaa75b590"
    )
