import math
from fractions import Fraction as Q
from itertools import product

import pytest

from sa02.intervals import (
    Interval as I,
)
from sa02.intervals import (
    contract_linear,
    interval,
    radial_contract,
    sincos,
    sqrt_bounds,
)
from sa02.oracle import hull, scalar_history, vertices


@pytest.mark.parametrize("x", [Q(0), Q(1), Q(4), Q(1, 9), Q(2), Q(1, 10**18), Q(10**6)])
def test_square_root_bounds_checked_exactly(x):
    r = sqrt_bounds(I(x, x))
    assert r.lo * r.lo <= x <= r.hi * r.hi
    assert r.width <= Q(1, 10**12)


@pytest.mark.parametrize(
    "angle",
    [
        Q(-8),
        Q(-4),
        Q(-3141592653589793, 10**15),
        Q(-1),
        Q(0),
        Q(1),
        Q(3141592653589793, 10**15),
        Q(4),
        Q(8),
    ],
)
def test_trig_interval_includes_separate_binary64_evaluation(angle):
    for halfwidth in [Q(0), Q(1, 1000), Q(1, 10), Q(3)]:
        s, c = sincos(I(angle - halfwidth, angle + halfwidth))
        for k in range(11):
            t = float(angle - halfwidth + 2 * halfwidth * Q(k, 10))
            assert float(s.lo) - 2e-15 <= math.sin(t) <= float(s.hi) + 2e-15
            assert float(c.lo) - 2e-15 <= math.cos(t) <= float(c.hi) + 2e-15


def test_trig_exact_origin():
    s, c = sincos(I(0, 0))
    assert s == I(0, 0) and c == I(1, 1)


@pytest.mark.parametrize("x,y", [(3, 4), (-3, 4), (3, -4), (-3, -4), (0, 5), (5, 0)])
def test_range_boundary_is_retained(x, y):
    out = radial_contract(I(x - 1, x + 1), I(y - 1, y + 1), I(5, 5))
    assert out is not None and out[0].contains(x) and out[1].contains(y)


def test_radial_contradiction():
    assert radial_contract(I(3, 4), I(4, 5), I(0, 1)) is None


@pytest.mark.parametrize("number", range(12))
def test_linear_contractor_contains_exact_reference_vertices(number):
    bounds = [(-2, 2), (-1, 1)]
    constraints = [((1, 1), Q(number - 6, 10), Q(number + 2, 10)), ((2, -1), Q(-3, 2), Q(3, 2))]
    points = vertices(bounds, constraints)
    cells = tuple(I(*b) for b in bounds)
    for _ in range(4):
        for a, low, high in constraints:
            if cells is not None:
                cells = contract_linear(cells, a, I(low, high))
    assert points and cells
    assert all(all(c.contains(v) for c, v in zip(cells, p, strict=True)) for p in points)
    exact = hull(points)
    assert all(c.lo <= lo <= hi <= c.hi for c, (lo, hi) in zip(cells, exact, strict=True))


def test_repeated_biased_observation_never_gets_independent_noise_credit():
    box = (I(-2, 2), I(-1, 1))
    target = I(-Q(1, 10), Q(1, 10))
    first = contract_linear(box, (1, 1), target)
    out = first
    for _ in range(50):
        out = contract_linear(out, (1, 1), target)
    assert out == first
    assert out[0] == I(-Q(11, 10), Q(11, 10))
    assert hull(vertices([(-2, 2), (-1, 1)], [((1, 1), target.lo, target.hi)]))[0] == (
        out[0].lo,
        out[0].hi,
    )


def test_independent_history_oracle_and_production_inequality_contractor():
    bounds = [(-2, 2), (-Q(1, 10), Q(1, 10)), (-Q(1, 2), Q(1, 2))]
    packets = [(0, Q(1, 4), Q(1, 10), 0), (2, Q(9, 20), Q(1, 10), 0)]
    exact = scalar_history(bounds, packets, 3)
    assert exact["vertices"]
    box = tuple(I(*b) for b in bounds)
    for _ in range(5):
        for t, y, e, known in packets:
            box = contract_linear(box, (1, t, 1), I(y - known - e, y - known + e))
    assert all(all(c.contains(v) for c, v in zip(box, p, strict=True)) for p in exact["vertices"])
    at3 = box[0] + box[1] * 3
    assert at3.lo <= exact["decision_hull"][0][0] <= exact["decision_hull"][0][1] <= at3.hi
    assert scalar_history(bounds, packets + [(0, 10, 0, 0)], 3)["vertices"] == ()


def test_axis_box_is_not_an_attainability_certificate():
    points = vertices([(-1, 1), (-1, 1)], [((1, 1), 0, 0)])
    assert hull(points) == ((Q(-1), Q(1)), (Q(-1), Q(1)))
    assert (Q(1), Q(1)) not in points


def test_basic_interval_vertex_arithmetic():
    a, b = I(-Q(3, 2), Q(2, 3)), I(-Q(4, 3), Q(5, 7))
    for x, y in product((a.lo, a.hi), (b.lo, b.hi)):
        assert (a + b).contains(x + y) and (a * b).contains(x * y)
    assert interval(0).square() == I(0, 0)
