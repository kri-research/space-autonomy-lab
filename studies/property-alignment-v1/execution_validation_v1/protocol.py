"""Versioned JSON interface. This package has NO physical actuator backend."""

from fractions import Fraction as Q
import hashlib
import json

SCHEMA = "sal-execution-request/1"
METHODS = {
    "cart": ("lag_aware_common_command", "robust_predictive_prefix", "third_order_barrier"),
    "spacecraft": ("common_command",),
}
MAX_PACKET_BYTES = 262144


def strict_load(raw):
    if not isinstance(raw, (str, bytes)) or len(raw) > MAX_PACKET_BYTES:
        raise ValueError("Packet size/type")

    def pairs(items):
        out = {}
        for k, v in items:
            if k in out:
                raise ValueError("Duplicate key")
            out[k] = v
        return out

    def bad(value):
        raise ValueError("Nonfinite JSON")

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=bad)


def encode(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def identity(obj):
    return hashlib.sha256(encode(obj)).hexdigest()


def integer(value):
    if type(value) is not int or value < 0:
        raise ValueError("Nonnegative integer required")
    return value


def validate_request(req):
    if set(req) != {
        "schema",
        "id",
        "sequence",
        "domain",
        "method",
        "payload",
        "units",
        "mode",
        "budget_ns",
    }:
        raise ValueError("Request fields")
    if req["schema"] != SCHEMA or req["mode"] != "host_only":
        raise PermissionError("Only host timing is enabled")
    if not isinstance(req["id"], str) or not req["id"] or len(req["id"]) > 100:
        raise ValueError("Request identity")
    integer(req["sequence"])
    if req["units"] != "SI" or req["budget_ns"] != 1000000000 or type(req["budget_ns"]) is not int:
        raise ValueError("Frozen units/budget")
    if req["domain"] not in METHODS or req["method"] not in METHODS[req["domain"]]:
        raise ValueError("Unsupported adapter")
    if not isinstance(req["payload"], dict) or req["payload"].get("namespace") != "calibration":
        raise PermissionError("Timing study only accepts exposed calibration inputs")
    return req


def check_action(action, authority):
    if (
        not isinstance(action, (list, tuple))
        or len(action) != 2
        or any(isinstance(x, bool) for x in action)
    ):
        return False
    try:
        values = tuple(Q(str(x)) for x in action)
        return sum(x * x for x in values) <= Q(str(authority)) ** 2
    except (ValueError, TypeError, ZeroDivisionError):
        return False


def normalized(pred, domain):
    raw = pred.get("status")
    positives = {"prefix", "certified_common_prefix"}
    negatives = {"obstruction", "proved_no_common_held_command"}
    label = "prefix" if raw in positives else "obstruction" if raw in negatives else "unresolved"
    return {
        "status": label,
        "raw_status": raw,
        "action": pred.get("action") if label == "prefix" else None,
        "scope": "finite_held_command_only",
        "physical_execution": False,
        "prediction": pred,
    }


def delay_compatibility(
    roundtrip_ns,
    model_delay_ns,
    *,
    sensor_upper_ns=None,
    actuator_upper_ns=None,
    alignment_upper_ns=None,
    clock_interval_upper_ns=None,
):
    """Explicit upper-bound timing test; unknown physical components remain unknown.

    Early arrival means a command must wait until the modelled application instant.
    A positive budget is NOT authority to act, and this test never certifies dynamics.
    """
    integer(roundtrip_ns)
    integer(model_delay_ns)
    items = (sensor_upper_ns, actuator_upper_ns, alignment_upper_ns, clock_interval_upper_ns)
    for x in items:
        if x is not None:
            integer(x)
    lower_miss = roundtrip_ns > model_delay_ns
    if any(x is None for x in items):
        return {
            "status": "incompatible_host_lower_bound" if lower_miss else "unknown_physical_delays",
            "host_slack_ns": model_delay_ns - roundtrip_ns,
            "physical_compatibility_established": False,
        }
    upper = roundtrip_ns + sum(items)
    return {
        "status": "compatible_with_supplied_bounds" if upper <= model_delay_ns else "late",
        "host_slack_ns": model_delay_ns - roundtrip_ns,
        "total_delay_upper_ns": upper,
        "wait_until_model_application": upper <= model_delay_ns,
        "physical_compatibility_established": False,
    }


class SimulatedCommandSink:
    """Virtual scheduler only. No serial, network or robot transport is implemented."""

    def __init__(self):
        self.actions = []
        self.seen = set()
        self.aborts = []
        self.stopped = False

    def submit(
        self,
        request_id,
        decision,
        *,
        earliest_arrival_ns,
        latest_arrival_ns,
        apply_at_ns,
        authority,
        same_clock=True,
        estop=False,
        proof_checked=False,
    ):
        for x in (earliest_arrival_ns, latest_arrival_ns, apply_at_ns):
            integer(x)
        if earliest_arrival_ns > latest_arrival_ns:
            raise ValueError("Reversed arrival bounds")
        reasons = []
        if request_id in self.seen:
            reasons.append("duplicate")
        self.seen.add(request_id)
        if type(same_clock) is not bool or not same_clock:
            reasons.append("clock_unaligned")
        if type(estop) is not bool or estop:
            self.stopped = True
        if self.stopped:
            reasons.append("emergency_stop")
        if decision.get("status") != "prefix":
            reasons.append("no_positive_command")
        if proof_checked is not True:
            reasons.append("unverified")
        if not check_action(decision.get("action"), authority):
            reasons.append("input_bound")
        if latest_arrival_ns > apply_at_ns:
            reasons.append("late")
        if reasons:
            self.aborts.append({"id": request_id, "reasons": reasons})
            return {"scheduled": False, "reasons": reasons, "physical_actuation": False}
        self.actions.append(
            {"id": request_id, "apply_at_ns": apply_at_ns, "action": decision["action"]}
        )
        return {"scheduled": True, "apply_at_ns": apply_at_ns, "physical_actuation": False}
