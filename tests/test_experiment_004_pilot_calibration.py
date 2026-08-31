import json
from pathlib import Path

from kri_space_autonomy.experiment_004_pilot.calibration import verify_calibration


def test_partition_41_calibration_is_reproducible_noninferential_and_selects_four_roots():
    result = verify_calibration(Path.cwd(), recompute=False)
    assert result["passed"], result
    assert result["selected_roots_per_case"] == 4
    assert result["pilot_outcomes_generated"] is False
    assert result["architecture_configuration_difference_computed"] is False


def test_calibration_records_exact_allowed_information_and_no_architecture_effect_inputs():
    evidence = json.loads(
        Path("experiments/004-pilot/calibration-evidence.json").read_text()
    )
    assert evidence["partition_code"] == 41
    assert evidence["status"] == "CALIBRATION_PASS"
    assert evidence["prohibited_information_used"] == []
    assert evidence["hazard_discordance_computed"] is False
    assert evidence["scientific_hypothesis_selected"] is False
    assert evidence["controller_or_policy_selected_or_fitted"] is False
    assert evidence["forced_event_reachability"]["passed"]
    assert evidence["event_tolerance"]["passed"]
    assert evidence["fault_activation"]["passed"]
    assert evidence["filter_fault_sanity"]["passed"]
    assert evidence["actuation_and_disturbance_sanity"]["passed"]
    assert evidence["deterministic_replay"]["passed"]


def test_forced_event_calibration_has_exact_separable_patterns_for_every_root():
    evidence = json.loads(
        Path("experiments/004-pilot/calibration-evidence.json").read_text()
    )
    forced = evidence["forced_event_reachability"]["cases"]
    assert len(forced["P01_forced_collision"]) == 4
    assert all(row["collision"] and row["keep_out_entry"] for row in forced["P01_forced_collision"])
    assert all(
        not row["collision"] and row["keep_out_entry"]
        for row in forced["P02_forced_keep_out_only"]
    )
    assert all(
        not row["collision"]
        and not row["keep_out_entry"]
        and row["corridor_departure"]
        for row in forced["P03_forced_corridor_departure"]
    )


def test_calibration_evidence_does_not_materialize_partition_43_or_44():
    assert not Path("experiments/004-pilot/seeds").exists()
    assert not Path("results/experiment-004-pilot").exists()
    assert not Path("experiments/004-confirmatory").exists()
    assert not Path("results/experiment-004-confirmatory").exists()
