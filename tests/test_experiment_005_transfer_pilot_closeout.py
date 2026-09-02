import json
from pathlib import Path

from kri_space_autonomy.experiment_005_transfer_pilot_closeout import verify


def test_invalid_partition_52_attempt_is_preserved_and_verified():
    result = verify(Path.cwd())
    assert result["passed"], result
    assert result["status"] == "INVALID_ATTEMPT_VERIFIED"
    assert result["decision"] == "pilot_invalid_infrastructure_failure"
    assert result["materialization"]["root_rows"] == 20
    assert result["materialization"]["planned_episode_rows"] == 40
    assert result["terminal_failure"]["completed_blocks"] == 0
    assert result["terminal_failure"]["durable_episode_rows"] == 0
    assert result["terminal_failure"]["terminal_failures"] == 1
    assert result["partition_53"]["passed"] is True


def test_closeout_forbids_claims_replay_retry_and_partition_reuse():
    root = Path("results/experiment-005-transfer-pilot")
    audit = json.loads((root / "invalid-attempt-audit.json").read_text())
    analysis = json.loads((root / "analysis.json").read_text())
    reproducibility = json.loads((root / "reproducibility.json").read_text())
    qc = json.loads((root / "qc.json").read_text())
    assert audit["partition_reusable"] is False
    assert audit["retries_observed"] == 0
    assert audit["replacement_roots_observed"] == 0
    assert audit["partial_outcomes_used"] is False
    assert analysis["scientific_endpoints_evaluated"] is False
    assert analysis["architecture_benefit_claimed"] is False
    assert reproducibility["same_platform_replay_performed"] is False
    assert reproducibility["replay_invocations"] == 0
    assert qc["overall_passed"] is False
    assert qc["checks"]["zero_infrastructure_failures"] is False
    assert not (root / "shards").exists()
    assert not (root / "pilot-episodes.jsonl").exists()
