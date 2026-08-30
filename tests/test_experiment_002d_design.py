import json
from dataclasses import replace
from pathlib import Path

from kri_space_autonomy.experiment_002d.config import (
    COMBINED_STRATUM,
    load_combined_information_config,
)
from kri_space_autonomy.experiment_002d.seeds import materialize_scenario_002d


def _historical_root_ids() -> set[str]:
    root_ids: set[str] = set()
    for directory in (
        Path("experiments/002/seeds"),
        Path("experiments/002b/seeds"),
        Path("experiments/002c/seeds"),
    ):
        for path in directory.glob("*.jsonl"):
            for line in path.read_text(encoding="utf-8").splitlines():
                root_id = json.loads(line).get("root_seed_id")
                if root_id is not None:
                    root_ids.add(str(root_id))
    return root_ids


def test_original_eight_stratum_map_resolves_only_f7_as_missing():
    mapping = json.loads(
        Path("experiments/002d/confirmatory-stratum-map.json").read_text()
    )
    assert len(mapping["strata"]) == 8
    assert [item["confirmatory_id"] for item in mapping["strata"]] == [
        "F0_nominal",
        "F1_primary_range_bias",
        "F2_primary_dropout",
        "F3_monitor_channel_fault",
        "F4_shared_cause_navigation",
        "F5_persistent_model_upset",
        "F6_actuator_degradation",
        COMBINED_STRATUM,
    ]
    missing = [
        item["confirmatory_id"]
        for item in mapping["strata"]
        if item["pilot_source"] is None
    ]
    assert missing == [COMBINED_STRATUM]


def test_information_size_is_exact_minimum_and_confirmatory_partition_is_untouched():
    study, _ = load_combined_information_config("experiments/002d/config.json")
    alpha = 1.0 - study.one_sided_confidence
    upper_298 = 1.0 - alpha ** (1.0 / 298)
    upper_299 = 1.0 - alpha ** (1.0 / 299)
    assert upper_299 < study.incomplete_block_limit <= upper_298
    assert study.information_seeds == 299
    assert study.planned_episodes == 598
    assert study.information_partition_code == 25
    assert study.information_partition_code != 16
    assert study.arms == ("D", "PD")


def test_f7_roots_are_disjoint_and_fault_schedule_matches_original_bounds():
    study, production = load_combined_information_config("experiments/002d/config.json")
    historical = _historical_root_ids()
    observed: set[str] = set()
    for replicate in (0, 1, 149, 298):
        scenario = materialize_scenario_002d(study, production, replicate)
        assert scenario.root_seed_id not in historical
        assert scenario.root_seed_id not in observed
        observed.add(scenario.root_seed_id)
        assert scenario.stratum_id == COMBINED_STRATUM
        assert study.dropout_onset_min_s <= scenario.dropout_onset_s < study.dropout_onset_max_s
        assert study.dropout_duration_min_s <= (
            scenario.dropout_end_s - scenario.dropout_onset_s
        ) < study.dropout_duration_max_s
        assert study.actuator_onset_gap_min_s <= scenario.actuator_onset_gap_s < (
            study.actuator_onset_gap_max_s
        )
        assert scenario.actuator_onset_s == (
            scenario.dropout_onset_s + scenario.actuator_onset_gap_s
        )
        assert study.actuator_duration_min_s <= (
            scenario.actuator_end_s - scenario.actuator_onset_s
        ) < study.actuator_duration_max_s
        assert study.actuator_effectiveness_min <= scenario.actuator_effectiveness < (
            study.actuator_effectiveness_max
        )
        assert set(scenario.arm_run_order) == {"D", "PD"}


def test_information_cap_is_enforced():
    study, production = load_combined_information_config("experiments/002d/config.json")
    invalid = replace(study, information_seeds=401)
    try:
        invalid.validate(production)
    except ValueError as error:
        assert "299" in str(error) or "400" in str(error)
    else:
        raise AssertionError("information study above the cap was accepted")
