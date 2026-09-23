"""Exact and adversarial offline-oracle fixtures, separate from campaign evidence."""

from dataclasses import replace
from fractions import Fraction as Q
import math
import random
import pytest
from specification.contract import load_property, State, Verdict as V, HoldCoverage as H
from adjudication.interval import Interval, Box, rational_bounds
from adjudication.geometry import bounds, separation_witness, numerical_agreement_witness
from adjudication.polynomial import PolynomialArc, bernstein_range
from adjudication.engine import adjudicate
from adjudication.flow import split_times, propagate_schedule, Model


@pytest.mark.parametrize("operator", ["add", "subtract", "multiply", "divide"])
def test_outward_operations_enclose_exact_rational_corner_results(operator):
    rng = random.Random(1729)
    special = [
        0.0,
        math.nextafter(0.0, 1.0),
        -math.nextafter(0.0, 1.0),
        0.1,
        -0.3,
        2.0**-100,
        2.0**100,
    ]
    inputs = [(a, b) for a in special for b in special]
    inputs += [(rng.uniform(-100, 100), rng.uniform(-100, 100)) for _ in range(100)]
    for a, b in inputs:
        if operator == "divide" and (b == 0 or abs(b) < 1e-200):
            continue
        x, y = Interval.point(a), Interval.point(b)
        if operator == "add":
            out, truth = x + y, Q(a) + Q(b)
        elif operator == "subtract":
            out, truth = x - y, Q(a) - Q(b)
        elif operator == "multiply":
            out, truth = x * y, Q(a) * Q(b)
        else:
            out, truth = x / y, Q(a) / Q(b)
        assert Q(out.lo) <= truth <= Q(out.hi)
    a, b = Interval(-1.0, 2.0), Interval(3.0, 4.0)
    observed = {"add": a + b, "subtract": a - b, "multiply": a * b, "divide": a / b}[operator]
    for x in (-1, 2):
        for y in (3, 4):
            expected = {
                "add": Q(x + y),
                "subtract": Q(x - y),
                "multiply": Q(x * y),
                "divide": Q(x, y),
            }[operator]
            assert Q(observed.lo) <= expected <= Q(observed.hi)


@pytest.mark.parametrize("number", [0.0, math.nextafter(0.0, 1.0), 0.01, 2.0, 4.0, 1e-200, 1e200])
def test_square_root_is_checked_by_exact_squares(number):
    out = Interval.point(number).sqrt()
    assert Q(out.lo) ** 2 <= Q(number) <= Q(out.hi) ** 2


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf, True, "1"])
def test_nonfinite_or_untyped_state_is_rejected(bad):
    with pytest.raises((ValueError, TypeError, ArithmeticError, OverflowError)):
        Box.point([bad, -30, 0, 0])


def test_arithmetic_domains_fail_explicitly():
    with pytest.raises(ValueError):
        Interval(1.0, -1.0)
    with pytest.raises(ArithmeticError):
        Interval(-1.0, 1.0).reciprocal()
    with pytest.raises(ArithmeticError):
        Interval(-1.0, 0.0).sqrt()
    with pytest.raises(ArithmeticError):
        Interval.point(1e308) * 1e308
    with pytest.raises(ValueError):
        Box.point([0, -30, 0, 0, 0, 0])


@pytest.mark.parametrize(
    "x,y,inside",
    [
        (0, -100, True),
        (0, -100.000001, False),
        (10, -100, True),
        (10.000001, -100, False),
        (3, -30, True),
        (3.000001, -30, False),
        (0, -27, True),
        (0, -26.999999, False),
        (2, -30, True),
        (0, -33, True),
        (2.5, -30, True),
        (0, -28, True),
        (0, -25, False),
        (0, -105, False),
        (-3, -30, True),
        (-3.000001, -30, False),
    ],
)
def test_independent_union_boundaries_match_declared_contract(x, y, inside):
    p = load_property()
    result = bounds(Box.point([x, y, 0, 0]), p)
    assert result["containment"] == (V.SATISFIED if inside else V.VIOLATED)
    assert p.classify(State(x, y, 0, 0))["inside_union"] == inside


@pytest.mark.parametrize(
    "radius,collision,keepout",
    [(1, True, True), (2, True, True), (5, False, True), (10, False, True), (11, False, False)],
)
def test_closed_collision_and_keepout_boundaries(radius, collision, keepout):
    result = bounds(Box.point([radius, 0, 0, 0]), load_property())
    assert (result["collision_free"] == V.VIOLATED) == collision
    assert (result["keep_out_free"] == V.VIOLATED) == keepout


@pytest.mark.parametrize("speed,hold", [(0, True), (0.05, True), (0.050001, False), (0.2, False)])
def test_speed_does_not_replace_position_requirement(speed, hold):
    result = bounds(Box.point([0, -30, 0, speed]), load_property())
    assert result["containment"] == V.SATISFIED
    assert result["hold"] == (H.ALL_ELIGIBLE if hold else H.NONE_ELIGIBLE)


def stationary(y, start=0, end=1):
    return PolynomialArc(Q(start), Q(end), ((Q(0),), (Q(y),), (Q(0),), (Q(0),)))


def test_uncertainty_uses_actual_state_box_not_historical_tolerance():
    p = load_property()
    small = Box.center_error([0, -26.999999, 0, 0], [0, 1e-8, 0, 0])
    large = Box.center_error([0, -26.999999, 0, 0], [0, 2e-6, 0, 0])
    assert bounds(small, p)["containment"] == V.VIOLATED
    assert bounds(large, p)["containment"] == V.UNRESOLVED
    assert separation_witness(small, p)["witness"]
    assert not separation_witness(large, p)["witness"]
    assert separation_witness(Box.point([0, -25, 0, 0]), p, Q(1, 10**9))["witness"]
    assert not separation_witness(Box.point([12, -99, 0, 0]), p)["witness"]
    assert bounds(Box.point([12, -99, 0, 0]), p)["containment"] == V.VIOLATED


def test_point_agreement_and_sampling_cannot_become_containment():
    p = load_property()
    assert (
        numerical_agreement_witness([[0, -30, 0, 0], [0, -30, 0, 0]], p)["status"] == "unresolved"
    )
    assert (
        numerical_agreement_witness([[0, -25, 0, 0], [0, -25.000001, 0, 0]], p)["status"]
        == "numerically_corroborated_violation"
    )
    for values in ([], [[0, -25, 0, 0]], [[0, -25, 0, 0], [0, math.nan, 0, 0]]):
        assert numerical_agreement_witness(values, p)["status"] == "unresolved"
    assert adjudicate([object()], p, end=1)["status"] == "unresolved"


def test_tangent_to_closed_union_is_contained_with_exact_polynomial_bounds():
    # y=-27-(t-1/2)^2 touches the permitted closed ellipse boundary.
    arc = PolynomialArc(Q(0), Q(1), ((Q(0),), (Q(-109, 4), Q(1), Q(-1)), (Q(0),), (Q(1), Q(-2))))
    out = adjudicate([arc], load_property(), end=1)
    assert out["status"] == "validated_containment"


def test_narrow_excursion_is_found_without_finite_grid_completeness_assumption():
    c = Q(129, 256)
    arc = PolynomialArc(
        Q(0), Q(1), ((Q(0),), (-27 + Q(1, 10**8) - c * c, 2 * c, Q(-1)), (Q(0),), (2 * c, Q(-2)))
    )
    p = load_property()
    assert all(bounds(arc.point(Q(i, 64)), p)["containment"] == V.SATISFIED for i in range(65))
    out = adjudicate([arc], p, end=1, minimum_width=Q(1, 65536))
    assert out["status"] == "validated_violation"
    a, b = out["first_exit_bracket_s"]
    truth = float(c - Q(1, 10000))
    assert a <= truth <= b and b - a <= 2 / 65536


def test_tangent_to_closed_collision_disk_is_a_violation():
    arc = PolynomialArc(Q(0), Q(1), ((Q(2),), (Q(-1, 2), Q(1)), (Q(0),), (Q(1),)))
    out = adjudicate([arc], load_property(), end=1)
    assert out["components"]["collision_free"] == V.VIOLATED
    assert out["witness_times_s"]["collision_free"] == 0.5


def test_endpoints_initial_membership_and_aborts_remain_distinct():
    p = load_property()
    for phase in ("approach", "holding", "abort"):
        assert p.classify(State(0, -105, 0, 0), phase)["inside_union"] is False
    out = adjudicate([stationary(-105, 0, 300)], p, aborted=True)
    assert out["status"] == "validated_violation" and out["initial_containment"] == V.VIOLATED
    hold = adjudicate([stationary(-30, 0, 300)], p, aborted=True)
    assert hold["hold_acquired"] == V.SATISFIED and hold["nominal_goal"] == V.VIOLATED
    end_collision = PolynomialArc(Q(0), Q(1), ((Q(3), Q(-1)), (Q(0),), (Q(-1),), (Q(0),)))
    out = adjudicate([end_collision], p, end=1)
    assert out["components"]["collision_free"] == V.VIOLATED
    assert out["witness_times_s"]["collision_free"] == 1


def test_continuous_dwell_uses_interval_bounds_and_respects_unresolved_cells():
    p = load_property()
    # Exact, continuous position/velocity with a constant value, no sample inference.
    out = adjudicate([stationary(-30, 0, 300)], p)
    assert out["hold_acquired"] == V.SATISFIED and Q(out["guaranteed_dwell_s"]) == 300
    assert adjudicate([stationary(-80, 0, 300)], p)["hold_acquired"] == V.VIOLATED
    # A broad enclosure at the speed limit remains ambiguous, never a false success.
    arcs = propagate_schedule(
        Model("hcw"), Box.center_error([0, -30, 0, 0.05], [0, 0, 0, 1e-6]), [(0, 0.25, (0, 0))]
    )
    short = adjudicate(arcs, replace(p, horizon=0.25, hold_dwell=0.25), minimum_width=Q(1, 64))
    assert short["hold_acquired"] != V.SATISFIED


def test_missing_overlap_resets_and_unsplit_events_fail_closed():
    p = load_property()
    for arcs in (
        [],
        [stationary(-30, 0, 0.5)],
        [stationary(-30, 0, 0.5), stationary(-30, 0.6, 1)],
        [stationary(-30, 0, 0.6), stationary(-30, 0.5, 1)],
        [stationary(-30, 0, 0.5), stationary(-31, 0.5, 1)],
    ):
        assert adjudicate(arcs, p, end=1)["status"] == "unresolved"
    assert adjudicate([stationary(-30)], p, end=1, required_events=[0.5])["status"] == "unresolved"


def test_command_disturbance_observation_and_fault_times_split_exactly():
    events = [Q(1, 3), Q(2, 7), Q(3, 8), Q(5, 7), Q(1)]
    knots = split_times(0, 1, Q(1, 4), events)
    assert set(events) <= set(knots)
    assert all(0 < b - a <= Q(1, 4) for a, b in zip(knots, knots[1:]))
    arcs = propagate_schedule(
        Model("hcw"),
        [0, -30, 0, 0],
        [(0, Q(1, 3), (0, 0)), (Q(1, 3), 1, (0, 0))],
        event_times=events,
    )
    assert (
        adjudicate(arcs, load_property(), end=1, required_events=events)["status"]
        == "validated_containment"
    )
    with pytest.raises(ValueError):
        propagate_schedule(Model("hcw"), [0, -30, 0, 0], [(0, 0.5, (0, 0)), (0.6, 1, (0, 0))])


def test_refinement_budget_cannot_manufacture_safety():
    arc = PolynomialArc(Q(0), Q(1), ((Q(0),), (Q(-109, 4), Q(1), Q(-1)), (Q(0),), (Q(1), Q(-2))))
    out = adjudicate([arc], load_property(), end=1, max_cells=1)
    assert out["status"] == "unresolved"


def test_bernstein_range_contains_exact_rational_evaluations():
    coefficients = (Q(2), Q(-3), Q(1), Q(5))
    lo, hi = bernstein_range(coefficients, Q(1, 3), Q(4, 3))
    for i in range(65):
        t = Q(1, 3) + Q(i, 64)
        truth = sum(c * t**k for k, c in enumerate(coefficients))
        assert lo <= truth <= hi
    assert rational_bounds(Q(-27)) == (-27.0, -27.0)


@pytest.mark.parametrize("y", [-30, -25])
def test_failed_interval_omits_whole_episode_separation_bound(monkeypatch, y):
    original = PolynomialArc.range

    def fail_later(self, a, b):
        if self.start >= Q(1, 2) and a < b:
            raise ArithmeticError("controlled enclosure failure")
        return original(self, a, b)

    monkeypatch.setattr(PolynomialArc, "range", fail_later)
    arcs = [stationary(y, 0, Q(1, 2)), stationary(y, Q(1, 2), 1)]
    result = adjudicate(arcs, load_property(), end=1)
    assert not result["complete_range_coverage"]
    assert not result["validated_containment"]
    assert "minimum_separation_enclosure_m" not in result
    assert result["status"] == ("unresolved" if y == -30 else "validated_violation")


def test_independent_classifier_does_not_call_point_contract(monkeypatch):
    from specification.contract import Property

    def forbidden(*args, **kwargs):
        raise AssertionError("Point implementation must not be reused as the oracle")

    monkeypatch.setattr(Property, "classify", forbidden)
    assert bounds(Box.point([0, -28, 0, 0]), load_property())["containment"] == V.SATISFIED
    assert bounds(Box.point([0, -25, 0, 0]), load_property())["containment"] == V.VIOLATED


def test_core_adjudication_has_no_online_or_historical_implementation_imports():
    from pathlib import Path
    import ast

    directory = Path(__file__).parents[1] / "adjudication"
    for name in ("interval", "series", "flow", "polynomial", "geometry", "engine"):
        tree = ast.parse((directory / (name + ".py")).read_text())
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and not node.level:
                imports.append(node.module or "")
        assert not any(
            n.startswith(("baseline", "validation", "kri_space_autonomy")) for n in imports
        ), (name, imports)
