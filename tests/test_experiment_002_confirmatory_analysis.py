from kri_space_autonomy.experiment_002_confirmatory.analysis import (
    _bootstrap_contrasts,
    _holm_adjust,
    _one_sided_discordance_p,
    validate_episode_cells,
)
from kri_space_autonomy.experiment_002_confirmatory.config import (
    CONFIRMATORY_STRATA,
    load_confirmatory_config,
)


def _row(stratum: str, root: str, arm: str, hazard: bool, success: bool) -> dict:
    return {
        "stratum_id": stratum,
        "root_seed_id": root,
        "arm": arm,
        "analysis_hazard": hazard,
        "physical_hazard_observed": hazard,
        "collision": False,
        "sustained_success": success,
        "braking_unreachable": False,
        "recovery_favorable_180": None if stratum == "F0_nominal" else success,
        "restricted_time_unrecovered_s_180": None
        if stratum == "F0_nominal"
        else (0.0 if success else 180.0),
        "minimum_braking_margin_m": 1.0,
        "minimum_range_m": 5.0,
        "handover_entries": 0,
        "fallback_duty_cycle": 0.0,
        "propellant_used_fraction": 0.1,
        "goal_dwell_final60_fraction": float(success),
        "recovery_state": "NOT_APPLICABLE"
        if stratum == "F0_nominal"
        else ("UNAFFECTED" if success else "NOT_RECOVERED"),
        "failure_class": None,
    }


def test_exact_cell_validator_accepts_the_frozen_32000_cell_shape():
    study, _ = load_confirmatory_config(
        "experiments/002-confirmatory/config.json"
    )
    rows = []
    for stratum in CONFIRMATORY_STRATA:
        for replicate in range(1000):
            root = f"synthetic:{stratum}:{replicate:04d}"
            for arm in study.arms:
                rows.append(_row(stratum, root, arm, False, True))
    result = validate_episode_cells(rows, study)
    assert result["structural_valid"]
    assert result["completeness_passed"]
    assert result["exact_expected_cells"]
    assert result["complete_four_arm_blocks"] == 8000


def test_paired_bootstrap_uses_fixed_stratum_weights_and_is_deterministic():
    study, _ = load_confirmatory_config(
        "experiments/002-confirmatory/config.json"
    )
    rows = []
    for stratum in CONFIRMATORY_STRATA:
        for replicate in range(10):
            root = f"bootstrap:{stratum}:{replicate:04d}"
            rows.extend(
                [
                    _row(stratum, root, "R", False, True),
                    _row(stratum, root, "D", True, False),
                    _row(stratum, root, "PS", False, True),
                    _row(stratum, root, "PD", False, True),
                ]
            )
    first, first_harm = _bootstrap_contrasts(rows, study, replicates=200, seed=123)
    second, second_harm = _bootstrap_contrasts(rows, study, replicates=200, seed=123)
    assert first == second
    assert first_harm == second_harm
    assert first["PD-D:analysis_hazard"]["estimate"] == -1.0
    assert first["PD-D:sustained_success"]["estimate"] == 1.0
    assert set(first_harm) == {
        "F3_monitor_channel_fault",
        "F4_shared_cause_navigation",
        "F6_actuator_degradation",
        "F7_combined_primary_dropout_actuator_degradation",
    }


def test_secondary_directions_and_holm_family_are_fixed():
    assert _one_sided_discordance_p(0, 10, "lower") < 0.01
    assert _one_sided_discordance_p(10, 0, "higher") < 0.01
    adjusted = _holm_adjust({"H3": 0.001, "H4": 0.02, "H5a": 0.03, "H5b": 0.9}, 0.05)
    assert adjusted["H3"]["rejected"]
    assert not adjusted["H5b"]["rejected"]
