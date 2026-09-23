"""Known-answer, assumptions, numerical and failure-handling baseline fixtures."""

import numpy as np
import pytest
from scipy.linalg import expm
from protective.common import (
    Observation,
    observation_to_information,
    Tube,
    SENSOR,
    W_COMPONENT,
    MODEL_COMPONENT,
    NUMERIC_COMPONENT,
    A,
    B,
    AC,
    BC,
    U_MAX,
    TARGET,
    absolute_maps,
    uncertain_ranges,
    pending_safe,
)
from protective.predictive import PredictiveFilter
from protective.barrier import BarrierFilter, forms
from protective.certificates import check_constants, ldl_positive, imat
from adjudication.interval import Box


@pytest.fixture(scope="module")
def ideal_tube():
    return Tube(np.zeros(4), MODEL_COMPONENT + NUMERIC_COMPONENT)


@pytest.fixture(scope="module")
def robust_tube():
    return Tube(SENSOR, W_COMPONENT + MODEL_COMPONENT + NUMERIC_COMPONENT)


@pytest.fixture(scope="module")
def predictive(ideal_tube):
    return PredictiveFilter(ideal_tube, horizon=160)


@pytest.fixture(scope="module")
def barrier(ideal_tube):
    return BarrierFilter(ideal_tube)


def info(s=(0.0, -97.5, 0.0, 0.12), error=(0.0, 0.0, 0.0, 0.0), kind="ideal"):
    return observation_to_information(Observation(0, 0, tuple(s), tuple(error), kind), 0, 0, {})


def test_terminal_conditions():
    result = check_constants()
    assert result["passed"], result


def test_not_every_positive_matrix_is_positive_definite():
    assert not ldl_positive(imat([[1.0, 2.0], [2.0, 1.0]]))[0]


@pytest.mark.parametrize("dt", [0.0, 0.125, 0.25, 1.0, 2.0])
def test_comparison_map_dominates_dynamics(dt):
    aa, bb = absolute_maps(dt)
    m = np.zeros((6, 6))
    m[:4, :4] = AC
    m[:4, 4:] = BC
    reference = expm(m * dt)
    assert np.all(aa + 1.0e-14 >= np.abs(reference[:4, :4]))
    assert np.all(bb + 1.0e-14 >= np.abs(reference[:4, 4:]))


@pytest.mark.parametrize("age,delay", [(0, 0), (1, 0), (0, 1), (1, 1)])
def test_information_history_respects_application_time(age, delay):
    history = {0: np.array([0.001, -0.002]), 1: np.array([-0.001, 0.001])}
    p = Observation(0, age, (0.0, -70.0, 0.0, 0.08), tuple(SENSOR))
    i = observation_to_information(p, age, age + delay, history)
    expected = np.array(p.value)
    for t in range(age + delay):
        expected = A @ expected + B @ history[t]
    np.testing.assert_allclose(i.estimate, expected, atol=1.0e-14)
    assert len(i.pending) == delay
    assert np.all(i.error >= SENSOR)


def test_missing_history_is_not_assumed_zero():
    with pytest.raises(ValueError):
        observation_to_information(
            Observation(0, 1, (0.0, -70.0, 0.0, 0.0), tuple(SENSOR)), 1, 2, {}
        )


@pytest.mark.parametrize(
    "value", [(np.nan, 0.0, 0.0, 0.0), (0.0, np.inf, 0.0, 0.0), (0.0, 0.0, 0.0)]
)
def test_malformed_observations_rejected(value):
    with pytest.raises(ValueError):
        Observation(0, 0, value, (0.0, 0.0, 0.0, 0.0))


def test_out_of_order_packet_rejected():
    with pytest.raises(ValueError):
        Observation(1, 0, (0.0, -30.0, 0.0, 0.0), tuple(SENSOR))


def test_excessive_information_age_rejected():
    with pytest.raises(ValueError):
        observation_to_information(
            Observation(0, 3, (0.0, -70.0, 0.0, 0.0), tuple(SENSOR)), 3, 3, {}
        )


def test_covariance_not_promoted_to_bound(predictive, barrier):
    uncertain = info(kind="covariance_only")
    for f in [predictive, barrier]:
        assert not f.decide(uncertain, np.zeros(2)).protected


@pytest.mark.parametrize("family", ["predictive", "barrier"])
def test_admissible_midpoint_first_control(family, ideal_tube):
    f = PredictiveFilter(ideal_tube, 160) if family == "predictive" else BarrierFilter(ideal_tube)
    result = f.decide(info(), np.array([0.0, 0.02]))
    assert result.protected and result.command is not None, result
    assert np.linalg.norm(result.command) <= U_MAX
    if family == "predictive":
        assert all(
            a.get("max_tightened_constraint_residual", -1) <= 0
            for a in result.details["attempts"]
            if a.get("passed")
        )
    else:
        assert (
            min(
                min(a["psi2_lower"])
                for a in result.details["attempts"]
                if a.get("checked_feasible")
            )
            >= 0
        )


@pytest.mark.parametrize("family", ["predictive", "barrier"])
def test_bounded_information_feasible(family, robust_tube):
    f = PredictiveFilter(robust_tube, 180) if family == "predictive" else BarrierFilter(robust_tube)
    r = f.decide(info(error=tuple(SENSOR), kind="deterministic_interval"), np.array([0.0, 0.02]))
    assert r.protected and np.linalg.norm(r.command) <= U_MAX, r


@pytest.mark.parametrize("family", ["predictive", "barrier"])
def test_outward_boundary_not_certified(family, ideal_tube):
    f = PredictiveFilter(ideal_tube, 160) if family == "predictive" else BarrierFilter(ideal_tube)
    r = f.decide(info((0.0, -27.0, 0.0, 0.12)), np.zeros(2))
    assert not r.protected and r.command is None


@pytest.mark.parametrize(
    "mode,state", [("approach", (0.0, -70.0, 0.0, 0.1)), ("hold", (0.0, -29.0, 0.0, 0.01))]
)
def test_degree_two_forms_against_direct_derivatives(mode, state):
    values = forms(Box.point(state), mode, (0.02, 0.04), 0.0)
    s = np.array(state)
    u = np.array([0.001, -0.002])
    a = (AC @ s)[2:] + u
    if mode == "approach":
        from protective.common import H, BAND

        expected = -H @ a - 0.06 * (H @ s[2:]) + 0.0008 * (BAND - H @ s[:2])
    else:
        q = s[:2] - TARGET[:2]
        D = np.diag([1 / 4, 1 / 9])
        h = 1 - q @ D @ q
        hd = -2 * q @ D @ s[2:]
        expected = [-2 * s[2:] @ D @ s[2:] - 2 * q @ D @ a + 0.06 * hd + 0.0008 * h]
    for row, value in zip(values, expected, strict=True):
        interval = row[2] + row[3][0] * float(u[0]) + row[3][1] * float(u[1])
        assert interval.lo - 1.0e-12 <= value <= interval.hi + 1.0e-12


def test_identical_position_different_velocity_domain():
    p = Box.point([0.0, -30.5, 0.0, 0.0])
    v = Box.point([0.0, -30.5, 0.0, 0.3])
    assert all(a[1].lo >= 0 for a in forms(p, "approach", (0.02, 0.04), 0.0))
    assert any(a[1].hi < 0 for a in forms(v, "approach", (0.02, 0.04), 0.0))


def test_union_component_not_intersection(barrier):
    # Above -30 is in the hold ellipse only; approach failure must not block H.
    r = barrier.decide(info((0.0, -29.0, 0.0, 0.0)), np.zeros(2))
    assert r.protected and r.details["component"] == "hold", r


def test_zero_thrust_is_not_stationary():
    s = np.array([1.0, -70.0, 0.0, 0.0])
    assert not np.array_equal(A @ s, s)


def test_solver_failure_no_plan_is_unresolved(ideal_tube):
    f = PredictiveFilter(ideal_tube, 160)
    r = f.decide(info(), np.zeros(2), force_solver_failure=True)
    assert r.command is None and not r.protected


def test_stored_plan_survives_solver_failure(ideal_tube):
    f = PredictiveFilter(ideal_tube, 160)
    first = f.decide(info(), np.array([0.0, 0.02]))
    assert first.protected
    state = A @ info().estimate + B @ first.command
    second = observation_to_information(
        Observation(1, 1, tuple(state), (0.0, 0.0, 0.0, 0.0), "ideal"), 1, 1, {0: first.command}
    )
    r = f.decide(second, np.array([0.0, 0.02]), force_solver_failure=True)
    assert r.protected and r.status == "stored_tube_feedback"
    assert r.details["backup_index"] == 1


def test_false_solver_success_rejected(predictive):
    i = info()
    radii = predictive.tube.radii(0.0, predictive.horizon)
    z = np.zeros((4, predictive.horizon + 1))
    u = np.full((2, predictive.horizon), 100.0)
    _, check = predictive.residuals(i.estimate, u, z, radii, 80)
    assert not check["passed"]


def test_barrier_forced_failure_no_false_safe(ideal_tube):
    result = BarrierFilter(ideal_tube).decide(info(), np.zeros(2), force_solver_failure=True)
    assert result.command is None and not result.protected


def test_pending_violation_is_not_hidden(ideal_tube):
    o = Observation(0, 0, (0.0, -27.0, 0.0, 0.12), (0.0, 0.0, 0.0, 0.0), "ideal")
    i = observation_to_information(o, 0, 1, {0: np.zeros(2)})
    assert not pending_safe(i, ideal_tube)


def test_large_uncertainty_cannot_use_small_terminal_set():
    t = Tube(np.array([1.0, 1.0, 0.1, 0.1]), 0.001)
    assert not t.valid_terminal


def test_arbitrary_bounded_disturbance_inside_comparison_enclosure():
    initial = np.array([0.0, -70.0, 0.0, 0.12])
    error = np.array([0.01, 0.01, 0.001, 0.001])
    u = np.array([0.002, -0.001])
    d = 0.0001
    boxes = uncertain_ranges(initial, error, u, d)
    s = initial + error
    aq, bq = __import__("protective.common", fromlist=["matrices"]).matrices(0.25)
    for j, box in enumerate(boxes):
        s = aq @ s + bq @ (u + np.array([d * (-1) ** j, d]))
        assert box.contains(s.tolist())
