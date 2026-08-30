from dataclasses import replace

import pytest

from kri_space_autonomy.experiment_003.config import ESTIMATOR_STRATA
from kri_space_autonomy.experiment_003_confirmatory.analysis import (
    _bootstrap_primary,
    _secondary_tests,
    validate_episode_cells,
)
from kri_space_autonomy.experiment_003_confirmatory.config import (
    load_confirmatory_config,
)


def _fixture_rows():
    seed_rows = []
    rows = []
    for stratum in ESTIMATOR_STRATA:
        for replicate in range(2):
            root = f"synthetic:{stratum}:{replicate}"
            seed_rows.append({"stratum_id": stratum, "root_seed_id": root})
            for arm in ("R", "D", "PS", "PD"):
                hazard = arm in {"R", "D"}
                rows.append(
                    {
                        "stratum_id": stratum,
                        "root_seed_id": root,
                        "arm": arm,
                        "failure_class": None,
                        "analysis_hazard": hazard,
                        "physical_hazard_observed": hazard,
                        "sustained_success": arm != "R",
                        "recovery_state": "RECOVERED" if stratum != "E0_nominal" else "NOMINAL",
                        "recovery_favorable_180": arm in {"PS", "PD"},
                        "restricted_time_unrecovered_s_180": 0.0 if arm in {"PS", "PD"} else 20.0,
                    }
                )
    return seed_rows, rows


def test_complete_cell_contract_uses_seed_manifest_as_schedule():
    study, _, _ = load_confirmatory_config("experiments/003-confirmatory/config.json")
    small = replace(study, roots_per_stratum=2)
    seed_rows, rows = _fixture_rows()
    result = validate_episode_cells(rows, seed_rows, small)
    assert result["structural_valid"], result
    assert result["completeness_passed"], result
    assert result["exact_expected_cells"]
    assert result["complete_four_arm_blocks"] == 14
    assert result["episode_rows"] == 56


def test_primary_bootstrap_is_paired_stratified_fixed_weight_and_deterministic():
    study, _, _ = load_confirmatory_config("experiments/003-confirmatory/config.json")
    small = replace(study, roots_per_stratum=2)
    _, rows = _fixture_rows()
    first = _bootstrap_primary(rows, small, replicates=200, seed=17)
    second = _bootstrap_primary(rows, small, replicates=200, seed=17)
    assert first == second
    assert first["analysis_hazard"]["estimate"] == -1.0
    assert first["analysis_hazard"]["two_sided_95_interval"] == pytest.approx([-1.0, -1.0])
    assert first["sustained_success"]["estimate"] == 0.0
    assert first["analysis_hazard"]["bootstrap_replicates"] == 200


def test_secondary_family_contains_only_h3_h4_h5a_h5b_with_one_holm_adjustment():
    study, _, _ = load_confirmatory_config("experiments/003-confirmatory/config.json")
    small = replace(study, roots_per_stratum=2)
    _, rows = _fixture_rows()
    result = _secondary_tests(
        rows,
        small,
        randomization_replicates=1000,
        randomization_seed=19,
    )
    assert set(result["tests"]) == {
        "H3_PS_minus_D_analysis_hazard",
        "H4_PD_minus_PS_analysis_hazard",
        "H5a_PD_minus_D_recovery_favorable",
        "H5b_PD_minus_D_restricted_time",
    }
    assert result["family_alpha"] == 0.05
    assert result["H5b_randomization"] == {"draws": 1000, "seed": 19}
