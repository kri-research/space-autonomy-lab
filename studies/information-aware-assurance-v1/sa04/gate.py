"""Small stateful simulation gate. No physical device backend is present."""

from copy import deepcopy

from iaa.types import identity, millis, primitive, rational

from .compute import ZERO, binding
from .legacy import protocol
from .wire import MODEL


class Gate:
    """Trusted checker-channel results only; not a malicious-checker defence.

    Initial queue/coast is preloaded in the simulated sink before the episode.
    A stopped Python parent is not claimed to leave real hardware protected.
    """

    def __init__(self, initial_input, prearm):
        self.initial_id = identity(initial_input)
        self.initial_input = deepcopy(initial_input)
        if prearm["initial_input_sha256"] != self.initial_id or prearm["model_sha256"] != identity(
            MODEL
        ):
            raise ValueError("Wrong initial protection record")
        self.arm = deepcopy(prearm)
        self.queue = tuple(map(rational, initial_input["queued_action"]))
        self.pending = None
        self.active = None
        self.last = -1
        self.seen = set()
        self.revoked = False

    def invalidate(self):
        self.revoked = True
        self.pending = None
        self.active = None

    def admit(self, result, expected_payload, ready_ms, *, checker_channel_ok=True):
        millis(ready_ms)
        why = []
        token = identity(expected_payload)
        if token in self.seen:
            why.append("duplicate")
        if len(self.seen) >= 4:
            why.append("capacity")
        else:
            self.seen.add(token)
        if ready_ms > 700 or ready_ms < expected_payload["input"]["at_ms"]:
            why.append("late_or_pre_request")
        if self.last >= 700 or self.pending is not None or self.active is not None:
            why.append("slot_consumed")
        if self.revoked or not self.arm["valid"]:
            why.append("initial_protection_unavailable")
        raw = expected_payload["input"]
        if any(
            raw[k] != self.initial_input[k]
            for k in ("initial", "sensors", "queued_action", "timing")
        ):
            why.append("changed_initial_contract")
        from sa02.model import history_prefix

        from .wire import history

        try:
            if (
                primitive(history_prefix(history(raw["history"]), 100))
                != self.initial_input["history"]
            ):
                why.append("changed_applied_history")
            original = {p["packet_id"]: p for p in self.initial_input["packets"]}
            actual = {p["packet_id"]: p for p in raw["packets"]}
            if any(actual.get(k) != v for k, v in original.items()):
                why.append("changed_observation_history")
        except (ValueError, KeyError, TypeError):
            why.append("malformed_history")
        if checker_channel_ok is not True:
            why.append("checker_channel_failure")
        try:
            if (
                result["schema"] != "iaa-action-check/4"
                or result["binding"] != binding(expected_payload)
                or result["scope"] != "HCW_variable_start_fixed_end_three_second_coast"
                or result["status"] != "checked_window_prefix"
                or result["full_recovery"] is not False
                or result["physical_validation"] is not False
                or result["uncertainty_sha256"] != identity(result["uncertainty"])
                or result["uncertainty"]["at_ms"] != expected_payload["input"]["at_ms"]
                or not protocol.check_action(expected_payload["action"], "1/50")
            ):
                why.append("binding_scope_or_check_mismatch")
        except (KeyError, TypeError, ValueError):
            why.append("malformed_check")
        if not why:
            self.pending = deepcopy(result)
        return dict(scheduled=not why, reasons=why)

    def tick(self, now_ms, *, live_binding_sha256=None):
        millis(now_ms)
        if now_ms < self.last:
            self.invalidate()
            raise ValueError("Monotonic clock regression")
        self.last = now_ms
        applied = False
        if (
            self.pending
            and now_ms >= 700
            and live_binding_sha256 != self.pending["binding"]["payload_sha256"]
        ):
            self.pending = None
        if self.pending:
            if 700 <= now_ms <= 710:
                self.active, self.pending = self.pending, None
                applied = True
            elif now_ms > 710:
                self.pending = None
        action = self.queue if now_ms < 200 else ZERO
        mode = "preloaded_finite_coast"
        if self.active and now_ms < 1200:
            action = tuple(map(rational, self.active["binding"]["action"]))
            mode = "checked_action"
        elif self.active:
            mode = "checked_finite_coast"
        credited = not self.revoked and self.arm["valid"] and now_ms < 4200
        if not credited:
            mode = "uncredited_after_expiry_or_invalidation"
        return dict(
            at_ms=now_ms,
            action=primitive(action),
            mode=mode,
            credited=credited,
            newly_applied=applied,
            changed_from_coast=bool(applied and any(action)),
            expires_ms=4200 if credited else 0,
            physical_actuation=False,
            live_binding_sha256=live_binding_sha256,
        )
