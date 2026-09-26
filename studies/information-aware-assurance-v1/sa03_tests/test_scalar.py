from fractions import Fraction as Q

import pytest

from sa03.scalar import examples, timing_case


def test_latest_time_and_maximum_braking_boundary():
    r = timing_case(Q(7, 10), Q(1, 5), Q(2, 5), 1, 1, Q(1, 4), Q(1, 100))
    assert r["latest_application_s"] == Q(5, 4)
    assert r["latest_acquisition_s"] == 1
    assert r["braking_recovery"]
    assert r["maximum_absolute_position_after_braking"] == 1
    late = timing_case(Q(7, 10), Q(1, 5), Q(2, 5), 1, Q(1001, 1000), Q(1, 4), Q(1, 100))
    assert late["waiting_containment"] and not late["braking_recovery"]


def test_closed_noise_support_overlap_blocks_distinguishing():
    r = timing_case(Q(7, 10), Q(1, 5), Q(2, 5), 1, Q(3, 4), Q(1, 4), Q(17, 20))
    assert not r["distinguishable_for_all_readings"]
    assert not r["braking_recovery"]


def test_counterexamples_are_retained():
    results = {r["name"]: r for r in examples()}
    assert results["timely_information"]["result"]["braking_recovery"]
    assert not results["information_too_late"]["result"]["braking_recovery"]
    assert not results["unsafe_wait"]["result"]["waiting_containment"]
    assert not results["existing_held_action_adequate"]["result"][
        "no_common_constant_command_through_horizon"
    ]
    assert "uncertainty_reduction_without_action_gain" in results


@pytest.mark.parametrize("u", [Q(k, 25) for k in range(-10, 11)])
def test_held_command_obstruction_with_separate_quadratic_evaluation(u):
    b, v, T = Q(7, 10), Q(1, 5), Q(2)
    ends = (b + v * T + u * T * T / 2, -b - v * T + u * T * T / 2)
    assert any(abs(q) > 1 for q in ends)


@pytest.mark.parametrize("delay", [Q(0), Q(1, 10), Q(1, 4), Q(1)])
def test_braking_trajectory_explicit_extrema(delay):
    b, v, U, L = Q(7, 10), Q(1, 5), Q(2, 5), Q(1)
    acquired = Q(1, 4)
    r = timing_case(b, v, U, L, acquired, delay)
    T = acquired + delay
    stop = v / U
    outward = b + v * T + v * stop - U * stop * stop / 2
    assert r["maximum_absolute_position_after_braking"] == outward
    assert r["braking_recovery"] == (outward <= L)
