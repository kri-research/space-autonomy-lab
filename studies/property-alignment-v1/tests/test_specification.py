"""Contract and analytical tests, with no research population or learned tuning."""

from dataclasses import replace
from fractions import Fraction as F
from pathlib import Path
import json
import math
import pytest
from specification.contract import (
    State,
    Information,
    ExecutionBounds,
    Verdict as V,
    HoldCoverage as H,
    IntervalEvidence,
    load_property,
    summarize_intervals,
)
from specification.analytical import (
    braking_distance,
    exact_state_recovery,
    endpoint_input_interval,
    quadratic_extrema,
)
from specification.fixtures import results
from validation.paths import evidence_root


@pytest.mark.parametrize(
    "x,y,inside",
    [
        (0, -100, True),
        (0, -27, True),
        (0, -25, False),
        (10, -100, True),
        (10.000001, -100, False),
        (3, -30, True),
        (3.000001, -30, False),
        (0, -100.000001, False),
        (2, -30, True),
        (0, -105, False),
    ],
)
def test_position_contract(x, y, inside):
    for phase in ("approach", "holding", "abort"):
        r = load_property().classify(State(x, y, 0, 0), phase)
        assert r["inside_union"] is inside
        assert r["recovery_status"] == "unassessed"
        assert r["scope"] == "point_only"


@pytest.mark.parametrize("v,eligible", [(0, True), (0.05, True), (0.050001, False), (100, False)])
def test_velocity_applies_to_holding_not_position(v, eligible):
    r = load_property().classify(State(0, -30, 0, v))
    assert r["inside_union"] and r["hold_eligible"] is eligible


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf, True, "1"])
def test_invalid_states_rejected(value):
    with pytest.raises(ValueError):
        State(value, -30, 0, 0)


def test_coordinate_and_units_drift_rejected(tmp_path):
    source = Path(__file__).parents[1] / "specification/property_contract.json"
    for key, value in [
        ("position_units", "km"),
        ("axes", ["radial_inward", "along_track"]),
        ("state_order", ["y_m", "x_m", "vx_mps", "vy_mps"]),
    ]:
        doc = json.loads(source.read_text())
        doc["frame"][key] = value
        p = tmp_path / "bad.json"
        p.write_text(json.dumps(doc))
        with pytest.raises(ValueError):
            load_property(p)
    with pytest.raises(TypeError):
        State(0, -30, 0, 0, 0, 0)


def test_geometry_matches_pinned_configuration_without_changing_it():
    cfg = json.loads((evidence_root() / "experiments/004/config.json").read_text())
    p = load_property()
    assert [p.lower_y, p.upper_y] == cfg["approach_y_bounds_m"]
    assert list(p.halfwidth) == cfg["hold_position_halfwidth_m"]
    assert p.hold_speed == cfg["hold_max_speed_mps"]
    assert p.command_limit == cfg["max_acceleration_mps2"]
    assert p.collision_radius == 2 and p.keep_out_radius == 10
    assert p.hold_dwell == 60 and p.horizon == 300
    assert p.classify(State(0, -105, 0, 0.12))["inside_union"] is False


def test_information_age_delay_and_covariance_are_distinct():
    packet = Information(
        2, 2.5, State(0, -80, 0, 0.1), (0.1, 0.1, 0.01, 0.01), "deterministic_interval"
    )
    timing = packet.timing(3, 3.5, 1, 0.5)
    assert timing["information_age_s"] == 1 and timing["intervention_delay_s"] == 0.5
    assert timing["within_declared_timing"]
    assert not timing["current_state_enclosure_produced"]
    assert not packet.timing(3, 3.5, 0.9, 0.5)["within_declared_timing"]
    cov = Information(0, 0, State(0, -80, 0, 0), None, "covariance_only")
    assert not cov.timing(0, 0, 0, 0)["has_deterministic_measurement_bound"]
    with pytest.raises(ValueError):
        replace(cov, error_bounds=(1, 1, 1, 1))
    with pytest.raises(ValueError):
        replace(packet, bound_kind="ideal")
    with pytest.raises(ValueError):
        packet.timing(2, 3, 1, 1)
    with pytest.raises(ValueError):
        packet.timing(3, 2, 1, 1)


def test_command_bound_is_separate_from_realized_disturbance():
    p = load_property()
    bounds = ExecutionBounds(0.5, 1, 0.001, 2, 0.3)
    assert p.validate_command((0.02, 0)) == (0.02, 0)
    assert bounds.realize(p, (0.02, 0), 1, (0.001, 0)) == (0.021, 0)
    with pytest.raises(ValueError):
        p.validate_command((0.02, 0.001))
    with pytest.raises(ValueError):
        bounds.realize(p, (0.01, 0), 0.49, (0, 0))
    with pytest.raises(ValueError):
        bounds.realize(p, (0.01, 0), 1, (0.002, 0))
    with pytest.raises(ValueError):
        ExecutionBounds(0.9, 0.8, 0, 0, 0)
    with pytest.raises(ValueError):
        ExecutionBounds(0, 1, math.inf, 0, 0)


def interval(start, end, hold=H.UNRESOLVED, containment=V.SATISFIED):
    return IntervalEvidence(start, end, containment, V.SATISFIED, V.SATISFIED, hold)


def test_temporal_evidence_not_point_sampling_and_no_abort_reset():
    p = load_property()
    r = summarize_intervals(p, [interval(0, 240), interval(240, 300, H.ALL_ELIGIBLE)])
    assert r["hold_acquired"] == V.SATISFIED and r["guaranteed_dwell_s"] == 60
    assert r["nominal_goal"] == V.SATISFIED
    violated = [interval(0, 240, containment=V.VIOLATED), interval(240, 300, H.ALL_ELIGIBLE)]
    r = summarize_intervals(p, violated)
    assert r["containment"] == V.VIOLATED and r["hold_acquired"] == V.SATISFIED
    assert r["nominal_goal"] == V.VIOLATED
    assert summarize_intervals(p, violated, aborted=True)["containment"] == V.VIOLATED
    with pytest.raises(ValueError):
        summarize_intervals(p, [replace(interval(0, 300), evidence_kind="samples_only")])
    with pytest.raises(ValueError):
        summarize_intervals(p, [interval(0, 299)])
    with pytest.raises(ValueError):
        summarize_intervals(p, [interval(0, 1), interval(2, 300)])
    with pytest.raises(ValueError):
        summarize_intervals(p, [interval(0, 2), interval(1, 300)])


def test_uncertain_interval_does_not_become_no_dwell():
    p = load_property()
    assert summarize_intervals(p, [interval(0, 300)])["hold_acquired"] == V.UNRESOLVED
    assert (
        summarize_intervals(p, [interval(0, 300, H.NONE_ELIGIBLE)])["hold_acquired"] == V.VIOLATED
    )
    r = summarize_intervals(p, [interval(0, 241), interval(241, 300, H.ALL_ELIGIBLE)])
    assert r["guaranteed_dwell_s"] == 59 and r["hold_acquired"] == V.UNRESOLVED


@pytest.mark.parametrize(
    "d,v,expected",
    [
        ("-1/10", "1/10", "initially_inadmissible"),
        ("1/2", "3/20", "admissible_but_unrecoverable"),
        ("1/2", "1/10", "demonstrably_recoverable"),
        ("1/4", "1/10", "demonstrably_recoverable"),
    ],
)
def test_position_and_recovery_separate_in_exact_scalar_model(d, v, expected):
    assert exact_state_recovery(d, v, "1/50") == expected


def test_exact_compound_braking_and_quantifier_counterexamples():
    out = results()
    assert out["compound_braking"]["joint_result"]["margin"] == F(-11, 50)
    q = out["common_policy_counterexample"]
    assert q["right_necessary_endpoint_interval"] == (F(-2, 5), F(-1, 5))
    assert q["left_necessary_endpoint_interval"] == (F(1, 5), F(2, 5))
    assert not q["common_first_input_exists"]
    assert not out["novelty_claim"] and not out["spacecraft_recovery_certificate"]


def test_endpoint_safety_does_not_certify_whole_segment():
    lo, hi, q, v = quadratic_extrema("9/10", "3/5", "-6/5", 1)
    assert q == F(9, 10) and hi == F(21, 20)
    assert endpoint_input_interval("9/10", "3/5", 1, "6/5") is not None


@pytest.mark.parametrize("bad", [True, 0.1, float("inf")])
def test_exact_fixture_rejects_inexact_inputs(bad):
    with pytest.raises(ValueError):
        braking_distance(bad, 0, 0, "1/50")


def test_pending_command_history_cannot_be_omitted_or_filled_implicitly():
    from specification.contract import HeldCommand, validate_pending_commands

    p = load_property()
    history = [HeldCommand(0, 1, (0.01, 0)), HeldCommand(1, 2.5, (0, -0.01))]
    validate_pending_commands(p, history, 0, 2.5)
    with pytest.raises(ValueError):
        validate_pending_commands(p, history, 0, 3)
    with pytest.raises(ValueError):
        validate_pending_commands(p, [], 0, 1)
    with pytest.raises(ValueError):
        validate_pending_commands(p, [history[0], HeldCommand(1.1, 2.5, (0, 0))], 0, 2.5)
    validate_pending_commands(p, [], 0, 0)


@pytest.mark.parametrize(
    "args", [("1/10", 0, 0, 0), ("-1/10", 0, 0, "1/50"), ("1/10", -1, 0, "1/50")]
)
def test_invalid_braking_assumptions_rejected(args):
    with pytest.raises(ValueError):
        braking_distance(*args)


def test_worst_case_braking_formula_matches_exact_quadratic_integration():
    for v in (F(0), F(1, 10), F(1, 5)):
        for a in (F(0), F(1, 100)):
            t, b = F(2), F(1, 50)
            _, _, distance, speed = quadratic_extrema(0, v, a, t)
            stopping_time = speed / b
            stop_distance = (
                distance
                if stopping_time == 0
                else quadratic_extrema(distance, speed, -b, stopping_time)[2]
            )
            assert braking_distance(v, t, a, b) == stop_distance


def test_abort_contract_cannot_silently_relax_the_property(tmp_path):
    source = Path(__file__).parents[1] / "specification/property_contract.json"
    for field in ("abort_relaxes_union", "abort_counts_as_nominal_completion"):
        doc = json.loads(source.read_text())
        doc[field] = True
        path = tmp_path / "contract.json"
        path.write_text(json.dumps(doc))
        with pytest.raises(ValueError):
            load_property(path)
    doc = json.loads(source.read_text())
    doc["phase_position_sets"]["abort"] = "unrestricted"
    path.write_text(json.dumps(doc))
    with pytest.raises(ValueError):
        load_property(path)


def test_serialized_analytical_fixture_matches_exact_execution():
    source = Path(__file__).parents[1] / "specification/analytical_fixtures.json"
    expected = json.loads(json.dumps(results(), default=str))
    assert json.loads(source.read_text()) == expected


def test_unknown_verdict_cannot_become_satisfied():
    from specification.contract import conjunction

    with pytest.raises(ValueError):
        conjunction(["unrecognized"])
    assert conjunction(iter([V.SATISFIED, V.UNRESOLVED])) == V.UNRESOLVED
