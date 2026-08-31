import json
from pathlib import Path

from kri_space_autonomy.experiment_004_pilot.config import (
    CASE_IDS,
    CONFIGURATIONS,
    FOUNDATION_FREEZE_ID,
    FOUNDATION_READINESS_ID,
    load_case_matrix,
    load_pilot_config,
)
from kri_space_autonomy.experiment_004_pilot.validation import (
    foundation_identity,
    information_boundary,
    matrix_and_gates,
    partition_44_inert,
)


def pilot():
    return load_pilot_config("experiments/004-pilot/config.json")


def cases():
    return load_case_matrix("experiments/004-pilot/case-matrix.json")


def test_pilot_design_has_exact_small_complete_block_matrix_and_count():
    config = pilot()
    matrix = cases()
    assert tuple(case.id for case in matrix) == CASE_IDS
    assert config.configuration_ids == CONFIGURATIONS
    assert config.pilot_roots_per_case == 4
    assert config.pilot_blocks == 44
    assert config.pilot_episodes == 88
    assert config.replay_blocks == 11
    assert config.replay_episodes == 22
    assert len({case.case_code for case in matrix}) == 11
    assert all(case.case_code == 100 * case.geometry_code + case.fault_code for case in matrix)


def test_matrix_covers_separate_physical_mission_channel_logic_shared_and_actuation_domains():
    observed = {case.domain for case in cases()}
    assert {
        "physical_geometry",
        "mission_feasibility",
        "primary_estimator",
        "monitor_estimator",
        "monitor_logic",
        "shared_cause",
        "actuation",
        "disturbance",
    } <= observed
    result = matrix_and_gates(Path.cwd(), pilot(), cases())
    assert result["passed"], result


def test_sample_count_rule_is_mechanical_not_inferential():
    config = pilot()
    assert config.candidate_roots_per_case == (2, 4, 6, 8)
    assert config.minimum_order_appearances_per_position_per_case == 2
    assert config.analysis_mode == "descriptive_mechanistic_gate_only"
    assert config.scientific_hypothesis_defined is False
    assert config.learned_policy_permitted is False
    gates = json.loads(Path("experiments/004-pilot/gates.json").read_text())
    analysis = gates["gates"]["analysis"]
    assert analysis["p_values_allowed"] is False
    assert analysis["superiority_or_noninferiority_tests_allowed"] is False
    assert analysis["architecture_effect_claims_allowed"] is False
    assert analysis["multiplicity_family_defined"] is False


def test_exact_foundation_identity_is_anchored_and_outcome_free():
    result = foundation_identity(Path.cwd())
    assert result["passed"], result
    assert result["freeze_id"] == FOUNDATION_FREEZE_ID
    assert result["readiness_id"] == FOUNDATION_READINESS_ID
    assert result["status"] == "READY_FOR_DESIGN_VALIDATION_PILOT"
    assert result["source_mismatches"] == []
    assert result["pilot_or_confirmatory_outcomes_materialized"] is False


def test_controller_and_monitor_online_boundary_has_no_privileged_inputs():
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


def test_partition_44_remains_reserved_unmaterialized_and_has_no_generator():
    result = partition_44_inert(Path.cwd(), pilot())
    assert result["passed"], result
    assert result["state"]["generator_available"] is False
    assert result["forbidden_symbols_found"] == []
    assert result["paths_present"] == []
