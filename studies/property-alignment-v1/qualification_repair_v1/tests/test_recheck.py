"""Stored flags cannot replace a concrete fixed-input proof."""

from copy import deepcopy
import pytest
from qualification_repair_v1.fixtures import inputs, information
from qualification_repair_v1.core import qualify
from qualification_repair_v1.recheck import recheck


def example():
    info = information(inputs()[0])
    return info, qualify(info)


def test_real_positive_rechecked():
    info, row = example()
    assert recheck(info, row)["passed"]


@pytest.mark.parametrize(
    "change",
    ["missing_hypothesis", "unbounded_action", "fake_identity", "recovery", "false_positive"],
)
def test_tampered_certificate_rejected(change):
    info, row = example()
    row = deepcopy(row)
    if change == "missing_hypothesis":
        row["hypotheses"].pop()
    if change == "unbounded_action":
        row["hypotheses"][0]["witness_action"] = ["1", "0"]
    if change == "fake_identity":
        row["information_sha256"] = "wrong"
    if change == "recovery":
        row["full_recovery_claim"] = True
    if change == "false_positive":
        row["physical_impossibility_claim"] = True
    with pytest.raises(ValueError):
        recheck(info, row)


def test_failed_recheck_stays_unresolved(monkeypatch):
    import qualification_repair_v1.recheck as module

    info, row = example()
    monkeypatch.setattr(module, "certify_action", lambda *a, **k: {"status": "unresolved"})
    assert not recheck(info, row)["passed"]
