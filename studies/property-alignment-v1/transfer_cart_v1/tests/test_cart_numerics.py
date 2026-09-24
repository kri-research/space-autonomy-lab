"""Analytical/calibration fixtures only; no protected family outcomes."""

from decimal import Decimal as D, localcontext
from fractions import Fraction as Q
import ast
from pathlib import Path
import pytest
from transfer_cart_v1.schema import NORMALS, validate, observe, mean_case, support
from transfer_cart_v1.arithmetic import Interval
from transfer_cart_v1.lag import maps, scalar_state, check_prefix
from transfer_cart_v1.reference import R, integrate, action_check, coefficient


def fixture(center=(0, 0, 0, 0, 0, 0), tau="0.3", delay="0"):
    return {
        "schema": "sal-lag-cart-case/1",
        "namespace": "calibration",
        "stratum": "unit_fixture",
        "index": 0,
        "generator_seed": "0",
        "tau": tau,
        "eta": "1",
        "authority": "0.4",
        "duration": "1",
        "delay": delay,
        "disturbance": "0",
        "boxes": [{"lower": list(map(str, center)), "upper": list(map(str, center))}],
        "packet_code": "unit",
        "measurement_time_s": "0",
    }


@pytest.mark.parametrize(
    "a,b", [("0.1", "0.3"), ("-0.2", "0.7"), ("1/3", "-2/7"), ("0", "0"), ("100", "0.001")]
)
def test_online_outward_arithmetic(a, b):
    x, y = Interval.of(a), Interval.of(b)
    for z, truth in ((x + y, Q(a) + Q(b)), (x * y, Q(a) * Q(b)), (x - y, Q(a) - Q(b))):
        assert Q(z.lo) <= truth <= Q(z.hi)


@pytest.mark.parametrize("tau", ["0.1", "0.3", "0.6"])
@pytest.mark.parametrize("t", ["0.125", "0.5", "1.25"])
def test_independent_flow_matches_analytic_decimal(tau, t):
    state = integrate((Q("0.2"), Q("-0.1"), Q("0.03")), Q("0.15"), Q("0.005"), Q(tau), Q(t))
    with localcontext() as ctx:
        ctx.prec = 100
        ta, tt = D(tau), D(t)
        e = (-tt / ta).exp()
        c = D("0.15")
        w = D("0.005")
        a = D("0.03")
        truth = (
            D("0.2")
            + D("-0.1") * tt
            + (c + w) * tt * tt / 2
            + (a - c) * (ta * tt - ta * ta * (1 - e)),
            D("-0.1") + (c + w) * tt + (a - c) * ta * (1 - e),
            c + (a - c) * e,
        )
    assert all(x.lower <= v <= x.upper for x, v in zip(state, truth, strict=True))
    f, g, _, _, _ = maps(Q(t), Q(tau))
    for online, reference in (
        (f, coefficient(Q(t), Q(tau), "initial_acceleration")),
        (g, coefficient(Q(t), Q(tau), "command")),
    ):
        assert online.lo <= reference.upper and reference.lower <= online.hi


def test_stationary_solution_and_zero_duration():
    state = integrate((0, 0, 0), 0, 0, Q("0.3"), 0)
    assert all(x.lower == x.upper == 0 for x in state)
    assert action_check(fixture(), (0, 0))["status"] == "contained"


def test_queue_violation_is_not_a_later_control_success():
    c = fixture((Q(".999"), 0, Q(".02"), 0, 0, 0), delay=".25")
    assert action_check(c, (-Q(".4"), 0))["status"] == "violation"


def test_nonzero_initial_actuator_changes_trajectory():
    c = fixture((0, 0, 0, 0, Q(".2"), 0))
    lag = scalar_state(c, c["boxes"][0], NORMALS[0], Q("0.5"))[0]
    instant = scalar_state(c, c["boxes"][0], NORMALS[0], Q("0.5"), instant=True)[0]
    assert lag.lo > instant.hi


def test_aliased_measurement_never_reveals_true_box():
    c = fixture((Q(".5"), 0, 0, 0, 0, 0))
    c["boxes"].append(fixture((Q("-.5"), 0, 0, 0, 0, 0))["boxes"][0])
    assert observe(c, c["boxes"][0]["lower"]) == observe(c, c["boxes"][1]["lower"])
    assert observe(c, (10, 0, 0, 0, 0, 0))["code"] == "inconsistent"
    assert all(Q(x) == 0 for x in mean_case(c)["boxes"][0]["lower"])


@pytest.mark.parametrize(
    "key,value",
    [
        ("tau", "0"),
        ("tau", "-1"),
        ("eta", "2"),
        ("authority", True),
        ("disturbance", "-1"),
        ("delay", "4"),
    ],
)
def test_invalid_physical_inputs(key, value):
    c = fixture()
    c[key] = value
    with pytest.raises(ValueError):
        validate(c)


def test_input_norm_bound_is_exact():
    c = fixture()
    assert action_check(c, (".4", ".001"))["status"] == "invalid_input"
    assert not check_prefix(c, (".4", ".001"))["passed"]


def test_support_corner_and_triangle_normals():
    for n in NORMALS:
        assert sum(x * x for x in n) == 1
        c = fixture()
        b = c["boxes"][0]
        b["lower"] = ["-1"] * 6
        b["upper"] = ["2"] * 6
        for k in range(3):
            assert support(b, n, k) >= support(b, n, k, False)


def test_reference_import_boundary():
    source = Path(__file__).resolve().parents[1] / "reference.py"
    imports = [
        n
        for n in ast.walk(ast.parse(source.read_text()))
        if isinstance(n, (ast.Import, ast.ImportFrom))
    ]
    assert not any(
        any(
            x in (getattr(n, "module", "") or "")
            for x in (
                "lag",
                "policies",
                "arithmetic",
                "candidate",
                "adjudication",
                "protective",
                "evaluation",
            )
        )
        for n in imports
    )
    assert "numpy" not in source.read_text() and "scipy" not in source.read_text()


def test_reference_range_detects_interior_excursion():
    from transfer_cart_v1.reference import enclose_curve

    # q=0.9+0.8t-0.8t^2 has safe endpoints but max1.1.
    coeff = list(map(R.value, ("0.9", "0.8", "-0.8")))
    result = enclose_curve(coeff, 0, Q(1))
    assert result["status"] == "violation"


def test_ambiguous_range_never_safe():
    from transfer_cart_v1.reference import enclose_curve

    result = enclose_curve([R.value(1)], D("0.01"), Q(1), max_cells=2)
    assert result["status"] == "unresolved"


def test_analytic_three_way_obstruction():
    from transfer_cart_v1.policies import obstruction
    from transfer_cart_v1.reference import dual_check

    c = fixture(tau="0.1")
    c["boxes"] = []
    for n in NORMALS:
        x = tuple(scale * k for scale in (Q(".95"), Q(".1"), Q(0)) for k in n)
        c["boxes"].append({"lower": list(map(str, x)), "upper": list(map(str, x))})
    cert = obstruction(c)
    assert cert["proved"] and dual_check(c, cert["weights"])["proved"]
    bad = list(cert["weights"])
    bad[0] = "-1"
    assert not dual_check(c, bad)["proved"]


def test_lag_dynamics_against_separate_ode_integrator():
    from scipy.integrate import solve_ivp
    import numpy as np

    tau = 0.3
    c = 0.15
    w = 0.005
    sol = solve_ivp(
        lambda t, z: (z[1], z[2] + w, (c - z[2]) / tau),
        (0, 1.25),
        (0.2, -0.1, 0.03),
        method="DOP853",
        rtol=1e-12,
        atol=1e-14,
        max_step=0.02,
    )
    ref = integrate((Q(".2"), Q("-.1"), Q(".03")), Q(".15"), Q(".005"), Q(".3"), Q("1.25"))
    assert sol.success
    assert np.max(np.abs(sol.y[:, -1] - [float(x.lower) for x in ref])) < 1e-10
