from dataclasses import replace
from fractions import Fraction as Q
from itertools import product

import pytest

from iaa.assurance import CommandSink, check
from iaa.enclosure import A, inside, propagate, step
from iaa.plant import flow
from iaa.types import Command, StateBox, Status, Uncertainty


def test_flow_against_independent_matrix_taylor():
    # Independent power-series solution of the affine ODE; no trigonometric map.
    for initial in [(1, -45, 0.05, 0.02), (-3, -32, -0.1, 0.3)]:
        for u in [(0.01, -0.01), (0, 0), (-0.02, 0)]:
            for duration in [0.01, 0.2, 1.0, 3.0]:
                result = list(map(float, initial))
                term = result.copy()
                for k in range(1, 30):
                    term = [
                        duration
                        / k
                        * (
                            sum(float(a) * v for a, v in zip(row, term, strict=True))
                            + (u[i - 2] if i >= 2 and k == 1 else 0)
                        )
                        for i, row in enumerate(A)
                    ]
                    result = [x + y for x, y in zip(result, term, strict=True)]
                assert flow(initial, u, duration) == pytest.approx(result, abs=2e-10)


def test_continuous_inclusion_covers_vertices_and_interior_times():
    box = StateBox.around((0.5, -45, 0.05, 0.02), (0.1, 0.2, 0.005, 0.01))
    action = (Q(1, 100), Q(-1, 100))
    endpoint, tube = step(box, action, 50)
    for vertex in product(*zip(box.lower, box.upper, strict=True)):
        for eta in [0.8, 1.0]:
            for w in [(-0.00001, -0.00001), (0.00001, 0.00001)]:
                for t in [0, 0.01, 0.025, 0.05]:
                    state = flow(vertex, action, t, eta, w)
                    # Binary64 comparison is corroboration; rational inclusion is the argument.
                    assert all(
                        float(lower) - 1e-10 <= v <= float(h) + 1e-10
                        for lower, v, h in zip(tube.lower, state, tube.upper, strict=True)
                    )
                state = flow(vertex, action, 0.05, eta, w)
                assert all(
                    float(lower) - 1e-10 <= v <= float(h) + 1e-10
                    for lower, v, h in zip(endpoint.lower, state, endpoint.upper, strict=True)
                )


def test_exact_stationary_enclosure_and_invalid_steps():
    box = StateBox.around((0, -45, 0, 0), (0, 0, 0, 0))
    end, _ = propagate(box, (0, 0), 3000, (Q(1), Q(1)), Q(0))
    assert end == box
    for dt in [-1, 0, 51, True]:
        with pytest.raises(ValueError):
            step(box, (0, 0), dt)


def setup():
    info = Uncertainty(StateBox.around((0, -45, 0, 0), (0.02, 0.02, 0.005, 0.005)), 100)
    cmd = Command((0, 0), 200, 700, "r")
    return info, cmd, check(info, cmd)


def test_protective_coast_has_entry_duration_and_expiry():
    info, cmd, proof = setup()
    assert proof.status == Status.BOUNDED_PREFIX and proof.valid_until_ms == 3700
    assert proof.recovery_claim is False
    bad = Uncertainty(StateBox.around((0, -30.01, 0, 0.25), (0, 0, 0, 0)), 100)
    failed = check(bad, cmd)
    assert failed.status == Status.UNRESOLVED  # not physical impossibility
    end, _ = propagate(bad.box, (0, 0), 200, (Q(1), Q(1)), Q(0))
    assert not inside(end)


def test_queued_command_is_checked_before_new_action():
    info = Uncertainty(StateBox.around((0, -30.001, 0, 0), (0, 0, 0, 0)), 0)
    cmd = Command((0, Q(-1, 50)), 200, 700, "q")
    proof = check(info, cmd, (0, Q(1, 50)))
    assert proof.status == Status.UNRESOLVED


def test_dispatch_lease_rejects_late_duplicate_unsupported_or_mismatched():
    info, cmd, proof = setup()
    sink = CommandSink()
    assert sink.submit(cmd, proof, info, 201) == {"scheduled": False, "reasons": ["late"]}
    assert "duplicate" in sink.submit(cmd, proof, info, 150)["reasons"]
    for bad in [
        replace(proof, status=Status.UNSUPPORTED),
        replace(proof, command_sha256="wrong"),
        replace(proof, valid_until_ms=700),
    ]:
        assert not CommandSink().submit(cmd, bad, info, 150)["scheduled"]
    assert CommandSink().submit(cmd, proof, info, 150)["scheduled"]


def test_no_silent_late_application_or_infinite_safe_stop():
    info, cmd, proof = setup()
    sink = CommandSink(initial_valid_until_ms=200)
    assert sink.submit(cmd, proof, info, 150)["scheduled"]
    assert sink.tick(199)[1] == "analysed_finite_coast"
    assert sink.tick(200)[2] == "r"
    assert sink.tick(699)[1] == "admitted_command"
    assert sink.tick(700)[1] == "analysed_finite_coast"
    assert sink.tick(3700)[1] == "uncredited_output_after_protection_expiry"
    with pytest.raises(ValueError):
        sink.tick(3699)
    other = CommandSink()
    other.submit(cmd, proof, info, 150)
    assert other.tick(201)[1] == "uncredited_output_after_protection_expiry"


def test_unsupported_set_or_interface_never_certifies():
    info, cmd, _ = setup()
    assert check(info, cmd, enabled=False).status == Status.UNSUPPORTED
    assert check(Uncertainty(None, 100, kind="unsupported"), cmd).status == Status.UNSUPPORTED


def test_unknown_scope_and_overextended_validity_never_authorize():
    info, cmd, proof = setup()
    with pytest.raises(ValueError, match="scope"):
        replace(proof, scope="unimplemented_other_model")
    extended = replace(proof, valid_until_ms=1000000)
    assert not CommandSink().submit(cmd, extended, info, 150)["scheduled"]


def test_expiry_cannot_be_extended_by_even_one_millisecond():
    info, cmd, proof = setup()
    assert CommandSink().submit(cmd, proof, info, 150)["scheduled"]
    for delta in (-1, 1, 3000):
        bad = replace(proof, valid_until_ms=proof.valid_until_ms + delta)
        assert "binding_or_scope_mismatch" in CommandSink().submit(cmd, bad, info, 150)["reasons"]


def test_terminal_dwell_thresholds_have_positive_and_negative_fixtures():
    from iaa.enclosure import terminal

    stationary = StateBox.around((0, -40, 0, 0), (0, 0, 0, 0))
    end, tubes = propagate(stationary, (0, 0), 2500, (Q(1), Q(1)), Q(0))
    assert end == stationary and all(terminal(t) for t in tubes)
    assert terminal(StateBox.around((0, -40, Q(1, 20), 0), (0, 0, 0, 0)))
    assert not terminal(StateBox.around((0, -40, Q(1, 20), Q(1, 20)), (0, 0, 0, 0)))
    assert not terminal(StateBox.around((Q(36, 100), -40, 0, 0), (0, 0, 0, 0)))
