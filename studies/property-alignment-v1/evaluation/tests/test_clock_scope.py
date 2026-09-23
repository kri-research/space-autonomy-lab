"""A deterministic CI clock must never leak into a protected evaluation."""

from copy import deepcopy
from unittest.mock import patch
import pytest
from evaluation.generator import case_payload
from evaluation.tests.clocked_fixture import run_case, perform
from candidate.fixtures import fixtures
from candidate.certify import decide


def test_clocked_worker_refuses_noncalibration_before_any_run(tmp_path):
    payload = deepcopy(case_payload("calibration", "interior_pair", 0))
    payload["namespace"] = "protected"
    with pytest.raises(PermissionError):
        run_case(payload)
    with pytest.raises(PermissionError):
        perform(payload, "episode", tmp_path / "never.json")
    assert not (tmp_path / "never.json").exists()


def test_real_policy_budget_semantics_remain_active():
    info = fixtures()["midpoint_known"]
    ticks = iter([0.0, 2.0, 2.0, 2.0, 2.0, 2.0])
    with patch("candidate.certify.time.perf_counter", side_effect=lambda: next(ticks, 2.0)):
        result = decide(info, budget_s=1.0)
    assert result["deadline_exceeded"]
    assert result["status"] == "unresolved_budget"
    assert result["action"] is None
