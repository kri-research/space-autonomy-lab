"""Versioned stateless adapter to the preserved SA02/SA04 bounded checker.

Every call reconstructs uncertainty and checks the actual proposed command.
Returned diagnostics are not reusable command-authority certificates.
"""

from copy import deepcopy

from . import __version__
from ._vendor.iaa.types import identity, millis, primitive
from ._vendor.sa04 import wire
from ._vendor.sa04.compute import check_action, estimate, initial_arm
from ._vendor.sa04.gate import Gate
from .integrity import verify_installation

SCHEMA = "kri-assurance-assessment/1"
RESULT_SCHEMA = "kri-assurance-result/1"


def contract():
    return dict(
        schema=SCHEMA,
        component_version=__version__,
        model=deepcopy(wire.MODEL),
        mode="offline_simulation_assessment",
        bounds_origin="declared_not_physically_calibrated",
    )


def _same(a, b):
    return wire.dumps(a) == wire.dumps(b)


def make_request(
    initial, current, action, *, ready_ms=675, apply_ms=700, assumptions_supported=True
):
    return dict(
        contract=contract(),
        initial_input=deepcopy(initial),
        current_input=deepcopy(current),
        proposed_action=deepcopy(action),
        ready_ms=ready_ms,
        apply_ms=apply_ms,
        assumptions_supported=assumptions_supported,
    )


def observation_packet(
    packet_id, sequence, channel, value, acquired_ms, available_ms, timestamp_uncertainty_ms=2
):
    """Encode one packet with the exact public frame, units and inherited schema."""
    from ._vendor.iaa.types import ObservationPacket

    packet = ObservationPacket(
        packet_id,
        sequence,
        channel,
        value,
        acquired_ms,
        available_ms,
        timestamp_uncertainty_ms,
        "m" if channel == "range" else "rad",
    )
    return wire.loads(wire.dumps(primitive(packet)))


def estimate_snapshot(snapshot):
    """Return a positive-use outer set. Never accept a supplied covariance as a bound."""
    verify_installation()
    raw = wire.loads(wire.dumps(snapshot))
    out, _, _, _ = estimate(raw)
    return dict(
        status=out.status,
        at_ms=out.at_ms,
        uncertainty=primitive(out),
        uncertainty_sha256=out.identity(),
        outer_set_only=True,
        attainable_negative_witness=False,
        physical_calibration=False,
    )


def assess(request):
    """Assess one finite episode. Malformed/unsupported input carries no authority."""
    response = dict(
        schema=RESULT_SCHEMA,
        component_version=__version__,
        status="unsupported_input",
        candidate_applied_in_simulation=False,
        physical_actuation=False,
        full_recovery=False,
        conformance_claim=False,
        realtime_claim=False,
        external_validation=False,
        transferable_authority=False,
    )
    try:
        provenance = verify_installation()
        req = wire.loads(wire.dumps(request))
        wire.exact(
            req,
            (
                "contract",
                "initial_input",
                "current_input",
                "proposed_action",
                "ready_ms",
                "apply_ms",
                "assumptions_supported",
            ),
        )
        if not _same(req["contract"], contract()):
            raise ValueError("Version, model or evidence-scope mismatch")
        if type(req["assumptions_supported"]) is not bool:
            raise ValueError("Explicit assumption state required")
        ready, apply = millis(req["ready_ms"]), millis(req["apply_ms"])
        if apply < 700 or apply > 4300:
            raise ValueError("Only the stated finite simulation interval is supported")
        response.update(request_sha256=identity(req), source_commit=provenance["source_commit"])
        if not req["assumptions_supported"]:
            return response | dict(status="assumptions_unavailable", reason="No protection claim")
        initial, current = req["initial_input"], req["current_input"]
        for key in ("initial", "sensors", "timing", "queued_action"):
            if not _same(initial[key], current[key]):
                raise ValueError("Initial and checking assumptions differ")
        # Reject alteration of received history before computing an actionable result.
        from ._vendor.sa02.model import history_prefix

        prefix = primitive(history_prefix(wire.history(current["history"]), 100))
        if not _same(prefix, initial["history"]):
            raise ValueError("Applied-history prefix changed")
        prior = {p["packet_id"]: p for p in initial["packets"]}
        actual = {p["packet_id"]: p for p in current["packets"]}
        if any(not _same(actual.get(k), v) for k, v in prior.items()):
            raise ValueError("Received observation history changed")
        arm = initial_arm(initial)
        payload = dict(input=current, action=req["proposed_action"])
        checked, _ = check_action(payload)
        gate = Gate(initial, arm)
        admitted = gate.admit(checked, payload, ready)
        emitted = gate.tick(apply, live_binding_sha256=identity(payload))
        if not arm["valid"]:
            status = "uncredited_entry"
        elif ready > 700:
            status = "late"
        elif checked["status"] != "checked_window_prefix":
            status = "unresolved"
        elif not admitted["scheduled"]:
            status = "rejected_binding"
        elif not emitted["newly_applied"]:
            status = "missed_application_window"
        else:
            status = "supported_prefix"
        response.update(
            status=status,
            initial_protection=arm,
            checked=checked,
            admission=admitted,
            simulated_output=emitted,
            candidate_applied_in_simulation=emitted["newly_applied"],
            effective_change_from_coast=emitted["changed_from_coast"],
            reason="Conditional finite-model assessment; not a physical command",
        )
        return primitive(response)
    except (ValueError, KeyError, TypeError, ArithmeticError, OSError, RecursionError) as exc:
        return response | dict(status="unsupported_input", reason=type(exc).__name__)


def record(request):
    """Create a reconstructable internal assessment, without host timing claims."""
    data = dict(schema="kri-assurance-replay/1", request=deepcopy(request), result=assess(request))
    return data | dict(sha256=identity(data))


def replay(receipt):
    """Recompute semantics as well as identity. Self-hashes do not authenticate provenance."""
    wire.exact(receipt, ("schema", "request", "result", "sha256"))
    if receipt["schema"] != "kri-assurance-replay/1":
        return False
    data = {k: v for k, v in receipt.items() if k != "sha256"}
    return identity(data) == receipt["sha256"] and _same(
        assess(receipt["request"]), receipt["result"]
    )
