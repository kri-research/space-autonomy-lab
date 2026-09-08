from __future__ import annotations

import json
from pathlib import Path


def test_experiment_005_confirmatory_closeout_is_exact_and_inconclusive() -> None:
    path = Path("docs/experiment-005-confirmatory-closeout.json")
    closeout = json.loads(path.read_text(encoding="utf-8"))

    assert closeout["schema"] == "kri-space-autonomy.experiment-005-confirmatory.closeout.v1"
    assert closeout["status"] == "closed_valid_inconclusive"
    assert closeout["partition_code"] == 53
    assert closeout["campaign"] == {
        "paired_blocks": 1068,
        "episode_rows": 2136,
        "validity_passed": True,
    }
    assert closeout["reproducibility"]["replay_byte_identical"] is True
    assert closeout["decision"] == "inconclusive"

    h1 = closeout["primary_gatekeeping"]["H1_physical_safety"]
    assert h1["passed"] is False
    assert h1["reference_adverse_gate_safe"] == 0
    assert h1["gate_adverse_reference_safe"] == 0
    assert h1["discordant_pairs"] == 0
    assert h1["paired_roots"] == 1068
    assert h1["gate_minus_reference_risk_difference"] == 0.0
    assert h1["one_sided_exact_p"] == 1.0

    h2 = closeout["primary_gatekeeping"]["H2_mission"]
    assert h2["status"] == "not_tested_primary_gate_closed"
    assert h2["passed"] is None
    assert h2["harmful_pairs"] == 0
    assert h2["paired_roots"] == 1068
    assert h2["harm_rate"] == 0.0

    integrity = closeout["integrity"]
    assert integrity["retries_used"] == 0
    assert integrity["replacement_roots_used"] == 0
    assert integrity["adaptive_extension_used"] is False
    assert integrity["outcome_driven_tuning_used"] is False
    assert integrity["endpoint_switching_used"] is False
    assert closeout["rerun_authorized"] is False
