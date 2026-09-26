import math

import numpy as np
import pytest

from sa05.dynamics import (
    NUMERIC_POSITION_M,
    NUMERIC_VELOCITY_MPS,
    N,
    Plant,
    R,
    inertial,
    mismatch_bound,
    numerical_adjudication,
    relative,
)
from sa05.reference import linear, nonlinear


@pytest.mark.parametrize("time", [0, 0.25, 1.2, 4.2])
@pytest.mark.parametrize("state", [(0, -40, 0, 0), (3, -55, 0.05, -0.1), (-7.9, -30.1, -0.1, 0.2)])
def test_frame_units_and_velocity_rotation(state, time):
    r, v = inertial(state, time)
    assert np.max(abs(np.asarray(relative(r, v, time)) - state)) < 2e-9
    assert np.linalg.norm(r) > R - 100


@pytest.mark.parametrize(
    "state,action,eta",
    [
        ((0, -45, 0, 0), (0, 0), 1),
        ((1, -45, 0.01, -0.02), (0.02, 0), 1),
        ((-2, -35, -0.03, 0.01), (0, -0.02), 0.8),
        ((-7.9, -30.2, 0.1, -0.04), (-0.02, 0), 1),
    ],
)
def test_basilisk_against_separate_nonlinear_ode(state, action, eta):
    w = (1e-6, -2e-6)
    p = Plant(state, eta, w)
    p.advance(200)
    p.advance(700, action)
    p.advance(1200, (-action[0], -action[1]))
    p.advance(4200)
    times = [r["at_ms"] / 1000 for r in p.rows]
    ref = nonlinear(
        state,
        [
            (0.2, (0, 0), eta, w),
            (0.7, action, eta, w),
            (1.2, (-action[0], -action[1]), eta, w),
            (4.2, (0, 0), eta, w),
        ],
        times,
    )
    err = np.abs(np.array([r["state"] for r in p.rows]) - np.array([r[1] for r in ref]))
    assert err[:, :2].max() < NUMERIC_POSITION_M / 10
    assert err[:, 2:].max() < NUMERIC_VELOCITY_MPS


def test_small_nonlinear_departure_fits_declared_uncertainty():
    p = Plant((1, -40, 0.01, 0.02))
    z = p.advance(4200, (0.02, 0))
    h = linear((1, -40, 0.01, 0.02), (0.02, 0), 4.2)
    assert np.max(np.abs(np.array(z) - h)) < 1e-5
    assert mismatch_bound() + 2e-6 < 1e-5
    assert abs(N - 0.0011) < 1e-15


def test_queue_is_applied_only_after_boundary_and_ends_on_time():
    a, b = Plant((0, -45, 0, 0)), Plant((0, -45, 0, 0))
    a.advance(700)
    b.advance(700)
    assert a.state() == b.state()
    a.advance(1200, (0, 0.02))
    b.advance(1200)
    assert a.state()[3] > b.state()[3] + 0.0099
    old = a.state()[3]
    a.advance(4200)
    assert abs(a.state()[3] - old) < 1e-4


def test_adjudication_has_distinct_ambiguous_and_violation_states():
    for y, expected in [(-40, "numerically_contained"), (-30, "ambiguous"), (-29, "violated")]:
        rows = [dict(at_ms=t, state=(0, y, 0, 0)) for t in range(0, 4201, 5)]
        out = numerical_adjudication(rows)
        assert out["constraint_status"] == expected
        assert out["mission_completion"] == (y == -40)
    with pytest.raises(ValueError):
        Plant((math.nan, 0, 0, 0))
