"""Model, Taylor-remainder and actual original-helper regression tests."""

from fractions import Fraction as Q
from types import SimpleNamespace
import math
import numpy as np
import pytest
from scipy.integrate import solve_ivp
from adjudication.interval import Interval, Box
from adjudication.series import Jet
from adjudication.flow import Model, make_arc, propagate_schedule, coefficients
from adjudication.extrema import bounded_extreme
from validation.loader import originals


@pytest.fixture(scope="module")
def old():
    return originals(expanded_cache=True)


@pytest.mark.parametrize("geometry", [2, 3])
@pytest.mark.parametrize("maximize", [True, False])
@pytest.mark.parametrize(
    "mode", ["failure", "nonfinite_fun", "nonfinite_x", "out_of_bracket", "inferior"]
)
def test_actual_original_helpers_and_versioned_sample_retention(
    old, geometry, maximize, mode, monkeypatch
):
    module = old[geometry]
    sign = 1 if maximize else -1

    def f(t):
        return sign * (1 - 8 * (t - 0.5) ** 2)

    def bad(fun, *, bounds, **kwargs):
        x = {"nonfinite_x": math.nan, "out_of_bracket": 2.0, "inferior": bounds[0]}.get(mode, 0.5)
        value = math.nan if mode == "nonfinite_fun" else fun(x)
        return SimpleNamespace(success=mode != "failure", x=x, fun=value)

    monkeypatch.setattr(module, "minimize_scalar", bad)
    historical = module._bounded_extreme(f, 1.0, maximize=maximize)[0]
    fixed = bounded_extreme(f, 1.0, maximize=maximize, optimizer=bad)
    assert fixed.value == sign and fixed.sampled_extreme == sign
    assert fixed.unresolved and not fixed.globally_certified
    if math.isfinite(historical):
        assert historical < 1 if maximize else historical > -1
    with pytest.raises(ArithmeticError):
        bounded_extreme(f, 1.0, maximize=maximize, optimizer=bad, require_resolved=True)


@pytest.mark.parametrize("mode", ["missing_fields", "exception", "reevaluation_exception"])
def test_optimizer_plugin_failures_keep_observed_evidence(mode):
    def f(t):
        if mode == "reevaluation_exception" and t == 0.501:
            raise RuntimeError("declared fixture")
        return 1 - 8 * (t - 0.5) ** 2

    def bad(*a, **kw):
        if mode == "exception":
            raise RuntimeError("declared fixture")
        if mode == "missing_fields":
            return SimpleNamespace(success=True)
        return SimpleNamespace(success=True, x=0.501, fun=-1.0)

    result = bounded_extreme(f, 1.0, maximize=True, optimizer=bad)
    assert result.value == 1 and result.unresolved and not result.globally_certified


def test_narrow_unsampled_extremum_remains_an_explicit_limitation(old):
    center = 0.50390625

    def f(t):
        return -1 + 0.01 * t + 2 * max(0.0, 1 - abs(t - center) / 1e-4)

    assert f(center) > 1
    for module in old[2:4]:
        assert module._bounded_extreme(f, 1.0, maximize=True)[0] < 0
    fixed = bounded_extreme(f, 1.0, maximize=True)
    assert fixed.value < 0 and not fixed.globally_certified


def test_nonfinite_objective_cannot_be_a_safe_result():
    with pytest.raises(ArithmeticError):
        bounded_extreme(lambda t: math.nan, 1.0, maximize=True)
    with pytest.raises(ValueError):
        bounded_extreme(lambda t: t, 1.0, maximize="true")


def test_fractional_power_jet_matches_exact_binomial_series():
    out = Jet(
        (Interval.point(1), Interval.point(1)) + (Interval.point(0),) * 7
    ).inverse_three_halves()
    value = Q(1)
    for k, c in enumerate(out.c):
        if k:
            value *= (-Q(3, 2) - (k - 1)) / k
        assert Q(c.lo) <= value <= Q(c.hi)


@pytest.mark.parametrize("kind", ["hcw", "nonlinear"])
def test_a_priori_flow_and_taylor_ranges_against_independent_numerical_solution(kind):
    model = Model(kind)
    initial = [0.5, -80.0, 0.01, 0.1]
    command = [0.001, -0.002]
    arc = make_arc(model, Box.point(initial), command, 0, 0.25)
    assert arc.contraction < 1
    n = math.sqrt(model.mu / model.radius**3) if kind == "nonlinear" else model.mean_motion

    def rhs(t, s):
        x, y, vx, vy = s
        if kind == "hcw":
            ax = 3 * n * n * x + 2 * n * vy + command[0]
            ay = -2 * n * vx + command[1]
        else:
            d = 2 * x / model.radius + (x * x + y * y) / model.radius**2
            inv = math.exp(-1.5 * math.log1p(d))
            radial = (
                -model.mu
                / model.radius**2
                * math.expm1(math.log1p(x / model.radius) - 1.5 * math.log1p(d))
            )
            ax = radial + 2 * n * vy + n * n * x + command[0]
            ay = -model.mu / model.radius**3 * y * inv - 2 * n * vx + n * n * y + command[1]
        return vx, vy, ax, ay

    ref = solve_ivp(
        rhs, (0, 0.25), initial, method="DOP853", rtol=1e-12, atol=1e-13, dense_output=True
    )
    assert ref.success
    for t in np.linspace(0, 0.25, 17):
        state = ref.sol(float(t))
        enclosure = arc.point(float(t))
        # Numerical reference rounding is independent of the exact-ODE enclosure.
        # This check is numerical agreement, not the justification of that enclosure.
        assert all(
            v.lo - 2e-12 <= float(s) <= v.hi + 2e-12
            for v, s in zip(enclosure.coordinates, state, strict=True)
        )
        assert arc.apriori.contains(Box.point(state.tolist()))
    assert max(arc.point(0.25).widths[:2]) < 1e-8


def test_hcw_constant_hold_is_exactly_enclosed_for_long_continuation():
    arcs = propagate_schedule(Model("hcw"), [0, -30, 0, 0], [(0, 2, (0, 0))])
    for arc in arcs:
        assert arc.range(arc.start, arc.end).contains([0, -30, 0, 0])
        assert max(arc.point(arc.end).widths) < 1e-10


def test_hcw_jet_coefficients_enclose_exact_recurrence():
    model = Model("hcw")
    n = Q(model.mean_motion)
    u = [Q(0.001), Q(-0.002)]
    initial = [Q(0.5), Q(-80), Q(0.01), Q(0.1)]
    c = coefficients(model, Box.point(initial), tuple(Interval.point(v) for v in u), 6)
    exact = initial
    for k in range(7):
        for j in range(4):
            assert Q(c[j][k].lo) <= exact[j] <= Q(c[j][k].hi)
        x, y, vx, vy = exact
        exact = [
            vx / (k + 1),
            vy / (k + 1),
            (3 * n * n * x + 2 * n * vy + (u[0] if k == 0 else 0)) / (k + 1),
            (-2 * n * vx + (u[1] if k == 0 else 0)) / (k + 1),
        ]


def test_unsupported_time_varying_or_singular_inputs_are_rejected():
    with pytest.raises(ValueError):
        make_arc(Model("hcw"), Box.point([0, -30, 0, 0]), [0, 0], 0, 1)
    with pytest.raises(ArithmeticError):
        make_arc(Model("nonlinear"), Box.point([-6778137, 0, 0, 0]), [0, 0], 0, 0.25)
    with pytest.raises(ValueError):
        Model("eccentric_chief")


def test_one_shot_time_events_split_command_disturbance_observation_and_faults():
    events = {"command": Q(1), "disturbance": Q(1, 4), "observation": Q(1, 3), "fault": Q(2, 7)}
    schedule = ((a, b, u) for a, b, u in [(0, 1, (0.001, 0)), (1, 2, (0, 0.001))])
    arcs = propagate_schedule(
        Model("hcw"), [0, -70, 0, 0], schedule, event_times=(v for v in events.values())
    )
    knots = {a.start for a in arcs} | {arcs[-1].end}
    assert set(events.values()) <= knots
    assert all(a.point(a.end) == b.point(b.start) for a, b in zip(arcs[:-1], arcs[1:]))


@pytest.mark.parametrize("initial", [[math.nan, -30, 0, 0], [0, -30, 0], [True, -30, 0, 0]])
def test_invalid_propagation_is_an_explicit_unresolved_episode(initial):
    from adjudication.engine import adjudicate_execution
    from specification.contract import load_property

    result = adjudicate_execution(Model("hcw"), initial, [(0, 300, (0, 0))], load_property())
    assert result["status"] == "unresolved" and not result["validated_containment"]


def test_consumed_status_generator_cannot_hide_uncertainty():
    from adjudication.engine import all_status
    from specification.contract import Verdict as V

    assert all_status(iter([V.UNRESOLVED, V.SATISFIED])) == V.UNRESOLVED
    with pytest.raises(ValueError):
        all_status([])


@pytest.mark.parametrize("destination", ["research", "historical"])
def test_validation_driver_cannot_write_into_either_repository(monkeypatch, tmp_path, destination):
    from adjudication import validate

    historical = tmp_path / "historical"
    historical.mkdir()
    monkeypatch.setenv("SAL_EVIDENCE_ROOT", str(historical))
    base = validate.ROOT if destination == "research" else historical
    output = base / "forbidden-validation-output"
    monkeypatch.setattr("sys.argv", ["validate", "--output", str(output)])
    with pytest.raises(ValueError, match="outside the research and historical"):
        validate.main()
    assert not output.exists()
