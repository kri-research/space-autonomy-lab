from pathlib import Path

from kri_space_autonomy.experiment_004_closeout import collect_evidence, verify_package


def test_completed_partition_45_evidence_is_exact_and_inconclusive() -> None:
    evidence = collect_evidence(Path.cwd())
    assert evidence["passed"], evidence
    assert evidence["decision"] == "inconclusive"
    assert evidence["counts"]["paired_blocks"] == 1452
    assert evidence["counts"]["episode_rows"] == 2904
    assert evidence["h1"]["passed"] is False
    assert evidence["h1"]["discordant_pairs"] == 0
    assert evidence["h2"]["status"] == "not_tested_primary_gate_closed"


def test_public_closeout_package_verifies_when_materialized() -> None:
    marker = Path("results/experiment-004-replacement-confirmatory/manifest.json")
    if marker.is_file():
        result = verify_package(Path.cwd())
        assert result["passed"], result
