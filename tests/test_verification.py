from kri_space_autonomy.verification import bounded_gate_check


def test_bounded_gate_check_passes():
    result = bounded_gate_check()
    assert result["passed"]
    assert result["checked_state_action_pairs"] > 0
