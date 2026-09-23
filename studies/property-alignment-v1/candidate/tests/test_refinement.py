"""Exact recovery-deadline verification, separate from preserved development."""

from fractions import Fraction as Q
import pytest
from candidate.refinement.scalar_recovery import viable, symmetric_deadline, witness, result
from candidate.scalar import action_is_safe, ScalarBox


def test_prefix_is_not_recovery():
    rows = result()
    assert rows["recovery_deadline_s"] == "1/4"
    half = next(r for r in rows["rows"] if r["blind_time_s"] == "1/2")
    assert half["safe_blind_prefix"] and not half["exact_recovery_feasible"]
    assert witness(Q(1, 4))["all_recover"]
    assert not witness(Q(2501, 10000))["all_recover"]


@pytest.mark.parametrize(
    "position,speed,authority",
    [(Q(9, 10), Q(1, 5), Q(2, 5)), (Q(1, 2), Q(1, 10), Q(1, 5)), (Q(4, 5), Q(1, 10), Q(1, 10))],
)
def test_complete_symmetric_deadline_identity(position, speed, authority):
    deadline = symmetric_deadline(position, speed, authority=authority)
    assert deadline is not None
    for delta in (Q(-1, 10000), Q(0), Q(1, 10000)):
        t = deadline + delta
        assert t > 0
        feasible = []
        for j in range(65):
            u = authority * Q(j - 32, 32)
            endpoint = all(
                viable(
                    sign * (position + speed * t) + u * t * t / 2,
                    sign * speed + u * t,
                    authority=authority,
                )
                for sign in (-1, 1)
            )
            feasible.append(endpoint)
        assert feasible[32] == (delta <= 0)
        if delta > 0:
            assert not any(feasible)
    pair = [
        ScalarBox(position, position, speed, speed),
        ScalarBox(-position, -position, -speed, -speed),
    ]
    assert action_is_safe(pair, 0, deadline, authority=authority)


def test_initially_unrecoverable_is_not_positive_deadline():
    assert symmetric_deadline(".99", ".2") is None
    assert not viable(".99", ".2")
    with pytest.raises(ValueError):
        symmetric_deadline(".9", 0)
