"""Prior-envelope finite-prefix checker and simulation-only command lease.

SA02 sensor-to-set inference and SA03 information-action selection remain absent.
The internal result object is not a cryptographic proof or untrusted plugin boundary.
"""

from fractions import Fraction as Q

from .enclosure import inside, propagate, separated
from .types import CHECK_SCOPE, CheckResult, Command, Status, Uncertainty, identity, millis

RESERVE_MS = 3000


def check(info: Uncertainty, command: Command, queued_action=(Q(0), Q(0)), *, enabled=True):
    stop = command.end_ms + RESERVE_MS

    def result(status, reason):
        return CheckResult(
            status, command.request_id, identity(command), identity(info), stop, reason
        )

    if not enabled:
        return result(Status.UNSUPPORTED, "checker_not_implemented_or_disabled")
    if info.box is None or info.kind != "propagated_initial_enclosure":
        return result(Status.UNSUPPORTED, "no_credited_deterministic_enclosure")
    if not 0 <= command.apply_ms - info.at_ms <= 200 or command.end_ms - command.apply_ms > 500:
        return result(Status.UNRESOLVED, "unsupported_queue_or_hold")
    # Validate the queued input with the same norm and SI contract.
    Command(tuple(queued_action), 0, 1, "queue-validation")
    box = info.box
    if not inside(box) or not separated(box):
        return result(Status.UNRESOLVED, "entry_enclosure_not_contained")
    schedule = [
        (queued_action, command.apply_ms - info.at_ms),
        (command.acceleration, command.end_ms - command.apply_ms),
        ((Q(0), Q(0)), RESERVE_MS),
    ]
    for action, dt in schedule:
        box, tubes = propagate(box, action, dt)
        if any(not inside(t) or not separated(t) for t in tubes):
            return result(Status.UNRESOLVED, "finite_prefix_or_coast_not_proved")
    return result(Status.BOUNDED_PREFIX, "rational_Picard_inclusion_under_declared_model")


class CommandSink:
    """Trusted single-process simulator, not an actuator or fault-isolated watchdog."""

    def __init__(self, initial_valid_until_ms=0):
        millis(initial_valid_until_ms)
        self.pending = None
        self.current = None
        self.valid_until_ms = initial_valid_until_ms
        self.seen = set()
        self.last_tick_ms = -1

    def submit(self, command, checked, info, ready_ms):
        millis(ready_ms)
        reasons = []
        if command.request_id in self.seen:
            reasons.append("duplicate")
        self.seen.add(command.request_id)
        if ready_ms > command.apply_ms:
            reasons.append("late")
        if ready_ms < info.at_ms:
            reasons.append("reply_before_request")
        if checked.status != Status.BOUNDED_PREFIX:
            reasons.append(checked.status.value)
        if (
            checked.command_sha256 != identity(command)
            or checked.information_sha256 != identity(info)
            or checked.request_id != command.request_id
            or checked.scope != CHECK_SCOPE
            or checked.valid_until_ms != command.end_ms + RESERVE_MS
        ):
            reasons.append("binding_or_scope_mismatch")
        if self.pending is not None:
            reasons.append("occupied_dispatch_slot")
        if command.apply_ms <= self.last_tick_ms:
            reasons.append("application_slot_already_passed")
        if reasons:
            return {"scheduled": False, "reasons": reasons}
        self.pending = (command, checked)
        return {"scheduled": True, "reasons": [], "apply_ms": command.apply_ms}

    def tick(self, now_ms):
        millis(now_ms)
        if now_ms < self.last_tick_ms:
            raise ValueError("Clock moved backwards")
        self.last_tick_ms = now_ms
        applied = None
        if self.pending is not None and self.pending[0].apply_ms == now_ms:
            self.current, checked = self.pending
            self.valid_until_ms = checked.valid_until_ms
            self.pending = None
            applied = self.current.request_id
        elif self.pending is not None and self.pending[0].apply_ms < now_ms:
            self.pending = None  # No silently shifted application instant.
        if self.current is not None and now_ms < self.current.end_ms:
            return self.current.acceleration, "admitted_command", applied
        if now_ms < self.valid_until_ms:
            return (Q(0), Q(0)), "analysed_finite_coast", applied
        return (Q(0), Q(0)), "uncredited_output_after_protection_expiry", applied
