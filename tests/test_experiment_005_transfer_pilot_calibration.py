import json
from pathlib import Path

from kri_space_autonomy.experiment_005_transfer_pilot.calibration import (
    verify_calibration,
)


def test_partition_51_calibration_is_reproducible_noninferential_and_selects_two_roots():
    result = verify_calibration(Path.cwd(), recompute=False)
    assert result["passed"], result
    assert result["selected_roots_per_case"] == 2
    assert result["pilot_outcomes_generated"] is False
    assert result["architecture_configuration_difference_computed"] is False
    assert result["partition_52_materialized"] is False
    assert result["partition_53_touched"] is False


def test_all_calibration_attempts_are_preserved_with_terminal_status():
    directory = Path("experiments/005-transfer-pilot")
    attempts = sorted(directory.glob("calibration-attempt-*.json"))
    assert len(attempts) == 4
    rows = [json.loads(path.read_text()) for path in attempts]
    assert [row["attempt_number"] for row in rows] == [1, 2, 3, 4]
    assert [row["status"] for row in rows] == [
        "CALIBRATION_EXCEPTION_TERMINAL",
        "CALIBRATION_EXCEPTION_TERMINAL",
        "CALIBRATION_FAIL",
        "CALIBRATION_PASS",
    ]
    provenance = json.loads((directory / "calibration-provenance.json").read_text())
    assert len(provenance["attempts"]) == 4
    assert all(item["preserved"] for item in provenance["attempts"])
    assert provenance["failed_attempts_deleted_or_retried"] is False


def test_final_calibration_passes_only_mechanical_checks():
    evidence = json.loads(
        Path("experiments/005-transfer-pilot/calibration-evidence.json").read_text()
    )
    assert evidence["status"] == "CALIBRATION_PASS"
    assert evidence["partition_code"] == 51
    assert evidence["prohibited_information_used"] == []
    assert evidence["experiment_004_outcomes_used"] is False
    assert evidence["architecture_benefit_or_hazard_discordance_computed"] is False
    assert all(check["passed"] for check in evidence["checks"].values())
    nominal = evidence["checks"]["nominal_transfer_feasibility"]
    assert nominal["physical_events_reported_but_not_used_as_a_favorable_gate"] is True
    mismatch = evidence["checks"]["model_mismatch_observability"]
    assert mismatch["absolute_favorable_or_unfavorable_threshold"] is None
    geometry = evidence["checks"]["truth_event_geometry_stability"]
    assert geometry["numerically_ambiguous"] is False
    assert geometry["certification_claimed"] is False


def test_calibration_does_not_materialize_partition_52_or_touch_53():
    assert not Path("experiments/005-transfer-pilot/seeds").exists()
    assert not Path("results/experiment-005-transfer-pilot").exists()
    assert not Path("experiments/005-confirmatory").exists()
    assert not Path("results/experiment-005-confirmatory").exists()
