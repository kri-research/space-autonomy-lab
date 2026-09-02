import json
from pathlib import Path

from kri_space_autonomy.experiment_005_transfer_pilot.config import (
    CASE_IDS,
    CONFIGURATIONS,
    load_case_matrix,
    load_pilot_config,
)
from kri_space_autonomy.experiment_005_transfer_pilot.validation import (
    information_boundary,
    matrix_and_gates,
)


def pilot():
    return load_pilot_config(root=Path.cwd())


def cases():
    return load_case_matrix()


def test_matrix_is_exact_small_noninferential_coverage_design():
    config = pilot()
    matrix = cases()
    assert tuple(case.id for case in matrix) == CASE_IDS
    assert config.configuration_ids == CONFIGURATIONS
    assert config.candidate_roots_per_case == (1, 2, 4)
    assert config.pilot_roots_per_case == 2
    assert config.pilot_blocks == 20
    assert config.pilot_episodes == 40
    assert config.replay_blocks == 10
    assert config.replay_episodes == 20
    assert len({case.case_code for case in matrix}) == 10
    assert all(
        case.case_code == 100 * case.geometry_code + case.challenge_code
        for case in matrix
    )


def test_matrix_covers_requested_transfer_fault_and_truth_domains():
    domains = {case.domain for case in cases()}
    assert {
        "nominal_transfer",
        "model_mismatch",
        "truth_event_geometry",
        "primary_estimator",
        "monitor_estimator",
        "monitor_logic",
        "shared_cause",
        "actuation",
        "disturbance",
    } <= domains
    result = matrix_and_gates(Path.cwd(), pilot(), cases())
    assert result["passed"], result
    assert all(
        counts == {"primary_reference": 1, "independent_monitor_gate": 1}
        for counts in result["within_case_order_coverage"].values()
    )


def test_mismatch_and_event_cases_are_isolated_mechanical_fixtures():
    matrix = {case.id: case for case in cases()}
    mismatch = matrix["T01_truth_model_mismatch_stress"]
    assert mismatch.fault == "none"
    assert mismatch.mechanics_noise_enabled is False
    assert mismatch.navigation_noise_enabled is False
    assert mismatch.initial_relative_state == (10.0, -100.0, 0.0, 0.14, -0.14, 0.0)
    event = matrix["T02_truth_keep_out_crossing_fixture"]
    assert event.fixture == "open_loop_truth_arc"
    assert event.fixture_command_mps2 == (0.0, 0.0)


def test_gates_forbid_inferential_architecture_and_hazard_claims():
    config = pilot()
    assert config.analysis_mode == "descriptive_mechanistic_gate_only"
    assert config.scientific_hypothesis_defined is False
    assert config.architecture_comparison_permitted is False
    gates = json.loads(Path("experiments/005-transfer-pilot/gates.json").read_text())
    analysis = gates["gates"]["analysis"]
    assert analysis["p_values_allowed"] is False
    assert analysis["superiority_or_noninferiority_tests_allowed"] is False
    assert analysis["hazard_rate_claims_allowed"] is False
    assert analysis["architecture_effect_claims_allowed"] is False
    assert analysis["model_mismatch_sign_interpreted_as_favorable_or_unfavorable"] is False


def test_online_control_boundary_contains_no_truth_case_root_or_fault_inputs():
    result = information_boundary()
    assert result["passed"], result
    assert result["prohibited_names_found"] == []
    assert result["control_function_parameters"] == [
        "primary_snapshot",
        "monitor_snapshot",
        "controller",
        "monitor",
        "configuration_id",
    ]
