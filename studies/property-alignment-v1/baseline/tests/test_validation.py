from __future__ import annotations
from types import SimpleNamespace
import numpy as np
import pytest
from validation.loader import originals, config, checked_source, SOURCES, FilterHealth
from validation.extrema import bounded_extreme
from validation.properties import inside_union, inside_hold


@pytest.fixture(scope="module")
def original():
    return originals(expanded_cache=True)


@pytest.mark.parametrize("name", list(SOURCES))
def test_source_byte_identity(name):
    checked_source(name)


@pytest.mark.parametrize("geometry_index", [2, 3])
@pytest.mark.parametrize("maximize", [False, True])
def test_actual_original_failure_regression(original, geometry_index, maximize, monkeypatch):
    g = original[geometry_index]
    f = (lambda t: 1 - 8 * (t - 0.5) ** 2) if maximize else (lambda t: 8 * (t - 0.5) ** 2 - 1)

    def fail(*args, **kwargs):
        return SimpleNamespace(success=False, x=0.5, fun=-1.0)

    monkeypatch.setattr(g, "minimize_scalar", fail)
    value, _ = g._bounded_extreme(f, 1.0, maximize=maximize)
    # Expected defect is asserted explicitly, not hidden as an xfail.
    assert value == (-1 if maximize else 1)
    fixed = bounded_extreme(f, 1.0, maximize=maximize, optimizer=fail)
    assert fixed.value == (1 if maximize else -1)
    assert fixed.unresolved and not fixed.globally_certified
    with pytest.raises(ArithmeticError):
        bounded_extreme(f, 1.0, maximize=maximize, optimizer=fail, require_resolved=True)


@pytest.mark.parametrize(
    "mode", ["failure", "nonfinite_fun", "nonfinite_x", "inferior", "out_of_bracket", "exception"]
)
@pytest.mark.parametrize("maximize", [False, True])
def test_sampled_evidence_preserved(mode, maximize):
    f = (lambda t: 1 - 8 * (t - 0.5) ** 2) if maximize else (lambda t: 8 * (t - 0.5) ** 2 - 1)
    sign = -1 if maximize else 1

    def bad(fun, *, bounds, **kwargs):
        if mode == "exception":
            raise RuntimeError("controlled fixture")
        x = bounds[0] if mode == "inferior" else 0.5
        if mode == "out_of_bracket":
            x = 0.0
        if mode == "nonfinite_x":
            x = float("nan")
        return SimpleNamespace(
            success=mode != "failure",
            x=x,
            fun=float("nan") if mode == "nonfinite_fun" else sign * f(x if np.isfinite(x) else 0.5),
        )

    got = bounded_extreme(f, 1.0, maximize=maximize, optimizer=bad)
    assert got.value == (1.0 if maximize else -1.0)
    assert got.unresolved


@pytest.mark.parametrize("maximize", [True, False])
def test_reject_nonfinite_sampled_objective(maximize):
    with pytest.raises(ArithmeticError):
        bounded_extreme(lambda t: np.nan if t == 0.5 else 0.0, 1.0, maximize=maximize)


@pytest.mark.parametrize("maximize", [True, False])
def test_tangent_extreme(maximize):
    f = (lambda t: -((t - 0.5) ** 2)) if maximize else (lambda t: (t - 0.5) ** 2)
    got = bounded_extreme(f, 1.0, maximize=maximize)
    assert abs(got.value) < 1e-14


@pytest.mark.parametrize("t", [0.0, 1.0])
def test_endpoint_extreme(t):
    f = (lambda s: s) if t == 1 else (lambda s: -s)
    got = bounded_extreme(f, 1.0, maximize=True)
    assert got.time_s == t


def test_narrow_unsampled_violation_is_not_certified(original):
    center = 0.50390625

    def f(t):
        return -1 + 0.01 * t + 2 * max(0.0, 1 - abs(t - center) / 1e-4)

    assert f(center) > 1
    for g in original[2:4]:
        assert g._bounded_extreme(f, 1.0, maximize=True)[0] < 0
    got = bounded_extreme(f, 1.0, maximize=True)
    assert got.value < 0 and not got.globally_certified


@pytest.mark.parametrize(
    "point,inside",
    [
        ((0.0, -100.0), True),
        ((0.0, -27.0), True),
        ((0.0, -25.0), False),
        ((0.0, -100.000001), False),
        ((3.0, -30.0), True),
        ((3.000001, -30.0), False),
        ((2.0, -30.0), True),
        ((0.0, -33.0), True),
        ((0.0, -26.999999), False),
        ((10.0, -100.0), True),
        ((10.000001, -100.0), False),
        ((0.0, -105.0), False),
    ],
)
def test_independent_membership_matches_actual_union(original, point, inside):
    assert inside_union(point) == inside
    state = np.array([*point, 0.0, 0.0, 0.0, 0.0])
    value = original[3].admissible_position_excess_m(state, config())
    assert (value <= 1e-12) == inside


class ConstantSegment:
    duration_s = 1.0

    def __init__(self, state):
        self.state = np.array(state)

    def state_at(self, t):
        return self.state

    def relative_state_at(self, t):
        return self.state


def test_actual_predicate_counterexample(original):
    c = config()
    old = original[2].evaluate_segment(ConstantSegment([0.0, -25.0, 0.0, 0.0]), c)
    new = original[3].admissible_position_excess_m(np.array([0.0, -25.0, 0.0, 0.0, 0.0, 0.0]), c)
    assert old.maximum_corridor_excess_m == -10
    assert not old.keep_out_entry
    assert new == pytest.approx(4 / 3)


@pytest.mark.parametrize("y", [-100.0, -30.0])
def test_e004_longitudinal_discontinuity(original, y):
    c = config()
    p = ConstantSegment([12.0, y, 0.0, 0.0])
    assert original[2].evaluate_segment(p, c).corridor_departure
    p.state[1] += -1e-6 if y == -100 else 1e-6
    assert not original[2].evaluate_segment(p, c).corridor_departure
    assert not inside_union(p.state)


@pytest.mark.parametrize(
    "r,collision,keepout",
    [
        (1.0, True, True),
        (2.0, True, True),
        (5.0, False, True),
        (10.0, False, True),
        (11.0, False, False),
    ],
)
def test_collision_keepout_nesting(original, r, collision, keepout):
    out = original[2].evaluate_segment(ConstantSegment([r, 0.0, 0.0, 0.0]), config())
    assert out.collision == collision and out.keep_out_entry == keepout


@pytest.mark.parametrize(
    "s,expected",
    [
        ([0.0, -30.0, 0.05, 0.0], True),
        ([0.0, -30.0, 0.050001, 0.0], False),
        ([2.0, -30.0, 0.0, 0.0], True),
        ([2.000001, -30.0, 0.0, 0.0], False),
    ],
)
def test_hold_position_and_speed(original, s, expected):
    assert inside_hold(s) == expected
    assert original[2].in_hold_region(np.array(s), config()) == expected


def snapshot(state, health=FilterHealth.VALID):
    return SimpleNamespace(
        time_s=0.0,
        mean=np.array(state),
        covariance=np.diag([0.01, 0.01, 0.0001, 0.0001]),
        health=health,
        prediction_only_age_s=0.0,
        consecutive_innovation_rejections=0,
    )


def test_actual_gate_accepts_outside_union(original):
    c = config()
    mod = original[4]
    controller = mod.DeterministicHoldController(c)
    gate = mod.EstimatedGeometryMonitor(c, controller, controller.controller_identity)
    s = snapshot([0.0, -25.0, 0.0, 0.0])
    proposal = controller.decide(mod.observation_from_snapshot(s))
    out = gate.gate(s, proposal)
    assert not out.overridden and not inside_union(s.mean)


def test_actual_degraded_fallback_can_leave_command_unchanged(original):
    c = config()
    mod = original[4]
    controller = mod.DeterministicHoldController(c)
    gate = mod.EstimatedGeometryMonitor(c, controller, controller.controller_identity)
    s = snapshot([0.0, -25.0, 0.0, 0.0], FilterHealth.DEGRADED)
    proposal = controller.decide(mod.observation_from_snapshot(s))
    out = gate.gate(s, proposal)
    assert out.overridden and out.reason == "ESTIMATOR_QUALITY"
    np.testing.assert_array_equal(out.executed_acceleration_mps2, proposal.acceleration_mps2)
    assert out.conservative_keep_out_radius_m is None


def test_cache_adapter_returns_identical_matrices(original):

    d4 = original[0]
    for t in np.linspace(0, 1, 65):
        a, b = d4._cached_discrete.__wrapped__(config().mean_motion_rad_s, float(t))
        ac, bc = d4.discrete_matrices(config().mean_motion_rad_s, float(t))
        np.testing.assert_array_equal(a, ac)
        np.testing.assert_array_equal(b, bc)


def test_analytical_vs_exponential_hcw_matrices(original):
    for t in [1e-4, 0.1, 0.25, 1.0, 60.0, 300.0]:
        a, b = original[0].discrete_matrices(config().mean_motion_rad_s, t)
        ac, bc = original[0].closed_form_matrices(config().mean_motion_rad_s, t)
        np.testing.assert_allclose(a, ac, rtol=1e-11, atol=1e-11)
        np.testing.assert_allclose(b, bc, rtol=1e-11, atol=1e-10)


def test_frame_roundtrip_three_dimensional(original):
    d5 = original[1]
    c = config()
    for phase in [0.0, 0.3, 1.7, 3.1]:
        chief = d5.circular_chief_state(
            c.gravitational_parameter_m3_s2, c.reference_radius_m, phase_rad=phase
        )
        for rho in [[1.0, -97.5, 2.0, 0.01, 0.12, -0.003], [-2.0, -30.0, -3.0, -0.02, 0.01, 0.004]]:
            out = d5.pair_to_relative(d5.pair_from_relative(chief, np.array(rho)))
            np.testing.assert_allclose(out[:3], rho[:3], rtol=0, atol=5e-9)
            np.testing.assert_allclose(out[3:], rho[3:], rtol=0, atol=5e-12)


@pytest.mark.parametrize("geometry_index", [2, 3])
@pytest.mark.parametrize("maximize", [False, True])
@pytest.mark.parametrize("mode", ["nonfinite_fun", "inferior_success"])
def test_actual_original_discards_better_sample(
    original, geometry_index, maximize, mode, monkeypatch
):
    g = original[geometry_index]
    f = (lambda t: 1 - 8 * (t - 0.5) ** 2) if maximize else (lambda t: 8 * (t - 0.5) ** 2 - 1)
    sign = -1 if maximize else 1

    def optimizer(fun, *, bounds, **kwargs):
        x = bounds[0]
        return SimpleNamespace(
            success=True, x=x, fun=float("nan") if mode == "nonfinite_fun" else sign * f(x)
        )

    monkeypatch.setattr(g, "minimize_scalar", optimizer)
    value, _ = g._bounded_extreme(f, 1.0, maximize=maximize)
    assert value < 1 if maximize else value > -1
    fixed = bounded_extreme(f, 1.0, maximize=maximize, optimizer=optimizer)
    assert fixed.value == (1 if maximize else -1)
    assert fixed.unresolved
