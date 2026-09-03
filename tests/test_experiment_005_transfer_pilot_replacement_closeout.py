from pathlib import Path

from kri_space_autonomy.experiment_005_transfer_pilot_replacement_closeout import (
    collect_evidence,
    verify_package,
)


def test_partition_54_execution_and_frozen_gates_validate() -> None:
    evidence = collect_evidence(Path.cwd())
    assert evidence["passed"], evidence
    assert evidence["seeds"]["root_rows"] == 20
    assert evidence["seeds"]["historical_root_overlap"] == 0
    assert evidence["seeds"]["partition_52_scenario_hash_overlap"] == 0
    assert evidence["execution"]["campaign"]["blocks"] == 20
    assert evidence["execution"]["campaign"]["episodes"] == 40
    assert evidence["execution"]["replay"]["blocks"] == 10
    assert evidence["execution"]["replay"]["episodes"] == 20
    assert evidence["qc"]["overall_passed"] is True
    assert all(check["passed"] for check in evidence["qc"]["checks"].values())


def test_closeout_is_descriptive_and_leaves_partition_53_untouched() -> None:
    evidence = collect_evidence(Path.cwd())
    analysis = evidence["analysis"]
    assert analysis["p_values_computed"] is False
    assert analysis["architecture_effect_estimated"] is False
    assert analysis["superiority_or_noninferiority_tested"] is False
    assert analysis["aggregate_observations"] == {
        "episodes": 40,
        "collision_count": 0,
        "keep_out_entry_count": 8,
        "corridor_departure_count": 40,
        "hold_acquired_count": 24,
    }
    assert analysis["progression"]["decision"] == "pilot_design_gates_passed"
    assert analysis["progression"]["confirmatory_design_freeze_scientifically_justified"]
    assert analysis["progression"]["confirmatory_partition_53_campaign_authorized"] is False
    assert evidence["identity"]["partition_53"]["passed"] is True


def test_public_closeout_package_verifies_when_materialized() -> None:
    marker = Path("results/experiment-005-transfer-pilot-replacement/manifest.json")
    if marker.is_file():
        result = verify_package(Path.cwd())
        assert result["passed"], result
