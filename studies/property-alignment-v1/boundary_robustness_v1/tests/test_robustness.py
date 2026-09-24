"""Adversarial family, scale, bound and time tests on the unchanged nominal triple."""

from copy import deepcopy
from fractions import Fraction as Q
import json
import pytest
from boundary_robustness_v1.core import (
    ROOT,
    ANCHORS,
    STATES,
    PAIRS,
    Parameters,
    evaluate,
    initial_margin,
    family_parameters,
    check_stress,
    projected,
    magnitude,
)
from boundary_robustness_v1.study import bisect_gate
from independent_hcw_audit_v1.arithmetic import Interval as I, dot, mv
from independent_hcw_audit_v1.hcw import N, maps, advance


@pytest.mark.parametrize(
    "field,value",
    [
        ("position_m", -1),
        ("velocity_mps", -1),
        ("mean_motion_relative", 2),
        ("queue_delay_s", 2),
        ("position_m", True),
        ("queue_delay_s", 0.1),
        ("position_m", "nan"),
        ("velocity_mps", "1/0"),
    ],
)
def test_bad_parameters(field, value):
    with pytest.raises((ValueError, TypeError, ZeroDivisionError)):
        Parameters(**{field: value})


def test_unchanged_reference_points_and_commands():
    assert STATES == (
        (Q(0), Q("-99.99905"), Q(0), Q("-.001")),
        (Q("7.99905"), Q(-80), Q(".001"), Q(0)),
        (Q("-7.99905"), Q(-80), Q("-.001"), Q(0)),
    )
    assert PAIRS == (
        ((0, 1), (Q("-.004"), Q(".004"))),
        ((0, 2), (Q(".004"), Q(".004"))),
        ((1, 2), (Q(0), Q("-.006"))),
    )
    assert N == Q(ANCHORS["mean_motion"])


def test_nominal_positive_and_joint_obstruction():
    r = evaluate(Parameters())
    assert all(r["gates"].values())
    assert Q(r["center_obstruction_margin_lower_m"]) > 0
    assert abs(float(Q(r["center_obstruction_margin_lower_m"])) - 6.396160160886677e-5) < 1e-15
    assert all(Q(row["residual_lower_m"]) > 0 for row in r["pair_bounds"])
    assert all(row["continuous_halfspace_checks"] == 256 * 2 * 4 for row in r["pair_bounds"])


def test_box_enlargement_is_not_uniform_shift_certificate():
    r = evaluate(Parameters(position_m=Q(1, 10000)))
    assert r["gates"]["information_boxes"]
    assert not r["gates"]["shifted_triples"]
    assert r["center_obstruction"] and not r["uniform_shifted_obstruction"]


def test_nonzero_combined_state_neighborhood():
    r = evaluate(Parameters(position_m=Q(1, 100000), velocity_mps=Q(1, 100000)))
    assert r["gates"]["shifted_triples"]


def test_initial_membership_independent_of_velocity():
    assert initial_margin(Q(0)) == initial_margin(Q(0))
    assert initial_margin(Q(0))["all_initial_boxes_in_corridor"]
    assert not initial_margin(Q(1, 1000))["all_initial_boxes_in_corridor"]


def test_exact_initial_boundary_and_outside():
    assert initial_margin(Q(19, 22000))["all_initial_boxes_in_corridor"]
    assert not initial_margin(Q(19, 22000) + Q(1, 10**15))["all_initial_boxes_in_corridor"]


def test_state_radius_does_not_affect_nominal_witness_obstruction():
    a = evaluate(Parameters())
    b = evaluate(Parameters(position_m=Q(1, 10000)))
    assert a["center_obstruction_margin_lower_m"] == b["center_obstruction_margin_lower_m"]
    assert Q(b["shifted_obstruction_margin_lower_m"]) < Q(a["shifted_obstruction_margin_lower_m"])
    assert a["family_id"] != b["family_id"]


def test_scaling_never_adds_meters_to_velocity():
    f = {"scale": ["1/1000", "1/10000", "1/100", "1/1000"]}
    p = family_parameters(f, Q(1, 2))
    assert p.position_m == Q(1, 2000) and p.velocity_mps == Q(1, 20000)
    assert p.mean_motion_relative == Q(1, 200) and p.queue_delay_s == Q(1, 2000)


def test_state_monotonicity_of_the_sufficient_bound():
    a = evaluate(Parameters(position_m=Q(1, 100000), velocity_mps=Q(1, 100000)))
    b = evaluate(Parameters(position_m=Q(1, 50000), velocity_mps=Q(1, 50000)))
    assert Q(a["shifted_obstruction_margin_lower_m"]) >= Q(b["shifted_obstruction_margin_lower_m"])
    for x, y in zip(a["pair_bounds"], b["pair_bounds"], strict=True):
        assert Q(x["residual_lower_m"]) >= Q(y["residual_lower_m"])


def test_model_and_delay_cover_whole_allowed_intervals():
    e, D = Q(1, 1000), Q(1, 1000)
    r = evaluate(Parameters(mean_motion_relative=e, queue_delay_s=D))
    assert r["n_interval_s_inverse"][0] != r["n_interval_s_inverse"][1]
    assert all(row["continuous_halfspace_checks"] == 2 * 256 * 2 * 4 for row in r["pair_bounds"])
    assert r["delay_interval_s"] == ["0", str(D)]


@pytest.mark.parametrize("d", [Q(0), Q(1, 1000), Q(1, 10), Q(1)])
def test_zero_queue_superposition_matches_sequential_response(d):
    state = tuple(I.value(x) for x in STATES[1])
    u = PAIRS[2][1]
    end = Q(1)
    delayed = advance(advance(state, (0, 0), d), u, end)
    phi, _ = maps(d + end, d + end)
    _, g = maps(end, end)
    direct = tuple(a + b for a, b in zip(mv(phi, state), mv(g, u), strict=True))
    assert all(x.overlaps(y) for x, y in zip(direct, delayed, strict=True))


def test_lipschitz_bound_encloses_independent_shift_corners():
    from itertools import product

    phi, _ = maps(Q(1, 2), Q(1))
    normal = (Q(1), Q(1, 10))
    pr = projected(phi, normal)
    radii = (Q(1, 10000),) * 2 + (Q(1, 100000),) * 2
    bound = sum(magnitude(x) * r for x, r in zip(pr, radii, strict=True))
    for signs in product((-1, 1), repeat=4):
        shift = tuple(s * r for s, r in zip(signs, radii, strict=True))
        # Test the exact coefficient-box support, not an outward-rounded dot
        # product that can exceed that mathematical support by one dyadic ULP.
        lower = sum(min(x.lower * s, x.upper * s) for x, s in zip(pr, shift, strict=True))
        upper = sum(max(x.lower * s, x.upper * s) for x, s in zip(pr, shift, strict=True))
        value = dot(pr, shift)
        assert lower >= -bound and upper <= bound
        assert value.lower <= lower and upper <= value.upper


def test_negative_coefficient_residual_is_charged():
    r = evaluate(Parameters(mean_motion_relative=Q(1, 100)))
    n = r["negative_details"]
    rhs = Q(n["weighted_rhs_upper_m"])
    residual = sum(Q(x) for x in n["coefficient_residual_upper_s2"])
    assert Q(n["center_margin_lower_m"]) == -rhs - Q(1, 50) * residual
    assert residual > 0


@pytest.mark.parametrize("index", range(3))
def test_explicit_stress_is_not_a_smaller_neighborhood_refutation(index):
    plan = json.loads((ROOT / "protocol.json").read_text())
    r = check_stress(plan["stress"][index])
    assert r["admissible_stress_realization"] and r["fixed_command_counterexample"]
    assert r["initial_status"] == "contained" and r["status"] == "outside"


def test_outside_initial_point_is_not_credited_as_a_departure():
    spec = deepcopy(json.loads((ROOT / "protocol.json").read_text())["stress"][0])
    spec["shift"] = ["1", "0", "0", "0"]
    assert not check_stress(spec)["fixed_command_counterexample"]


def test_bisection_is_prespecified_and_never_calls_noncertified_failure_physical():
    f = {"name": "test", "scale": ["1/1000", "0", "0", "0"]}
    visited = []

    def query(p):
        visited.append(p.position_m)
        return {"gates": {"shifted_triples": p.position_m < Q(1, 3000)}, "parameters": p.payload()}

    r = bisect_gate(f, "shifted_triples", query, 14)
    assert len(visited) == 16 and Q(r["lower_radius"]) < Q(1, 3) <= Q(r["noncertified_upper"])
    assert Q(r["noncertified_upper"]) - Q(r["lower_radius"]) == Q(1, 16384)


def test_passing_cap_is_not_reported_as_maximal():
    f = {"name": "test", "scale": ["0", "0", "1", "0"]}
    r = bisect_gate(
        f,
        "information_boxes",
        lambda p: {"gates": {"information_boxes": True}, "parameters": p.payload()},
        14,
    )
    assert r["cap_passed"] and r["noncertified_upper"] is None and len(r["probes"]) == 2


def test_failure_at_nominal_stops_claim():
    with pytest.raises(ValueError):
        bisect_gate(
            {"name": "test", "scale": ["0"] * 4},
            "shifted_triples",
            lambda p: {"gates": {"shifted_triples": False}, "parameters": p.payload()},
            14,
        )


def test_stated_protocol_matches_numerical_domain():
    from boundary_robustness_v1.core import SLICES

    plan = json.loads((ROOT / "protocol.json").read_text())
    assert SLICES == plan["time_cells_per_phase"] == 256
    assert plan["core_precision_bits"] == 192
    for family in plan["families"]:
        p = family_parameters(family, Q(1))
        assert p.queue_delay_s + 1 <= 3 and (p.n * I.value(p.queue_delay_s + 1)).upper < Q(1, 32)


def test_uniform_model_gain_covers_direct_corners():
    p = Parameters(
        position_m=Q(1, 100000),
        velocity_mps=Q(1, 200000),
        mean_motion_relative=Q(1, 1000),
        queue_delay_s=Q(1, 1000),
    )
    r = evaluate(p)
    radii = (p.position_m,) * 2 + (p.velocity_mps,) * 2
    for row, (pair, u) in zip(r["pair_bounds"], PAIRS, strict=True):
        bound = Q(row["residual_lower_m"])
        for index in pair:
            for sign in (-1, 1):
                z = tuple(x + sign * dx for x, dx in zip(STATES[index], radii, strict=True))
                n = N * (1 + sign * p.mean_motion_relative)
                phi, _ = maps(1 + p.queue_delay_s, 1 + p.queue_delay_s, n)
                _, g = maps(1, 1, n)
                point = tuple(dot(pr, z) + dot(gr, u) for pr, gr in zip(phi, g, strict=True))
                from boundary_robustness_v1.core import NORMALS, BOUNDS

                for a, b in zip(NORMALS, BOUNDS, strict=True):
                    assert b - dot(a, point[:2]).upper >= bound


def test_exact_monotone_display_rounding_and_frontier_semantics():
    from boundary_robustness_v1.presentation import downward, frontier

    for q in (Q(1, 3), Q(123456789, 1000000), Q(1, 100000000), Q(0)):
        assert Q(downward(q)) <= q
    data = frontier({"nominal": evaluate(Parameters())})
    assert {x["gate"] for x in data} == {"information_boxes", "shifted_triples"}
    assert all(
        x["strict_obstruction_boundary_excluded"] == (x["gate"] == "shifted_triples") for x in data
    )


def test_no_original_numerical_source_edited():
    import hashlib

    for name, h in ANCHORS["source_files"].items():
        assert hashlib.sha256((ROOT.parent / name).read_bytes()).hexdigest() == h


def test_noncertificate_margin_does_not_assert_counterexample():
    r = evaluate(Parameters(position_m=Q(1, 10000)))
    assert r["gates"]["information_boxes"] and not r["gates"]["shifted_triples"]
    assert (
        "not proof" in r["noncertified_meaning"] and not r["physical_or_sensor_performance_claim"]
    )
