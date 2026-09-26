"""Read-only causal/semantic replay; hashes do not establish physical truth."""

from copy import deepcopy

from iaa.types import identity, primitive, rational

from .compute import check_action, initial_arm
from .gate import Gate


def seal(events):
    result, previous = [], "0" * 64
    for sequence, event in enumerate(sorted(events, key=lambda e: e["at_ms"])):
        row = dict(
            schema="iaa-execution-event/4", sequence=sequence, previous=previous, **primitive(event)
        )
        row["sha256"] = identity(row)
        result.append(row)
        previous = row["sha256"]
    return dict(
        schema="iaa-execution-trace/4",
        events=result,
        count=len(result),
        terminal=previous,
        feedback_kind="simulation_only",
    )


def audit(trace):
    errors = []
    if (
        trace.get("schema") != "iaa-execution-trace/4"
        or trace.get("feedback_kind") != "simulation_only"
    ):
        return ["trace_scope"]
    events = trace.get("events", [])
    if not events or len(events) != trace.get("count"):
        return ["truncated_trace"]
    previous, last, gate = "0" * 64, -1, None
    current_payload = None
    checked = None
    observed = []
    latest_applied = None
    for i, row in enumerate(events):
        payload = {k: v for k, v in row.items() if k != "sha256"}
        if (
            row.get("sequence") != i
            or row.get("previous") != previous
            or identity(payload) != row.get("sha256")
        ):
            errors.append("trace_integrity")
        previous = row.get("sha256")
        at = row.get("at_ms")
        if type(at) is not int or at < last:
            errors.append("event_clock")
            continue
        last = at
        kind, detail = row.get("event"), row.get("data", {})
        try:
            if kind == "initial":
                if gate is not None or at != 100:
                    errors.append("repeated_initialization")
                raw = deepcopy(detail["input"])
                arm = initial_arm(raw)
                if arm != detail["arm"]:
                    errors.append("incorrect_initial_protection")
                gate = Gate(raw, arm)
                observed = list(raw["packets"])
            elif kind == "observation":
                if detail["available_ms"] > at:
                    errors.append("future_observation")
                observed.append(detail)
            elif kind == "check_input":
                current_payload = detail
                raw = detail["input"]
                if raw["at_ms"] != at:
                    errors.append("stale_estimate_input")
                if raw["packets"] != [p for p in observed if p["available_ms"] <= at]:
                    errors.append("observation_history_mismatch")
                checked = None
            elif kind == "check_result":
                expected, _ = check_action(current_payload)
                if primitive(expected) != detail:
                    errors.append("outdated_or_incorrect_certificate")
                checked = detail
            elif kind == "admission":
                result = gate.admit(
                    checked, current_payload, at, checker_channel_ok=detail["checker_channel_ok"]
                )
                if result != detail["outcome"]:
                    errors.append("invalid_admission")
            elif kind == "invalidate":
                gate.invalidate()
            elif kind == "command":
                live = detail.get("live_binding_sha256")
                if live is not None and (
                    current_payload is None or live != identity(current_payload)
                ):
                    errors.append("live_binding_mismatch")
                actual = gate.tick(at, live_binding_sha256=live)
                if actual != detail:
                    errors.append("incorrect_command_or_timing")
                if detail["changed_from_coast"] and not any(rational(v) for v in detail["action"]):
                    errors.append("unchanged_fallback_claimed_as_intervention")
                if detail["newly_applied"]:
                    latest_applied = detail
            elif kind == "acknowledgement":
                if detail["physical"] is not False or latest_applied is None:
                    errors.append("acknowledgement_scope")
                elif detail["action"] != latest_applied["action"] or at != latest_applied["at_ms"]:
                    errors.append("acknowledgement_mismatch")
            elif kind == "end":
                if at != 4300:
                    errors.append("incomplete_episode")
        except (ValueError, KeyError, TypeError, ArithmeticError, AttributeError):
            errors.append("malformed_semantic_event")
    if previous != trace.get("terminal"):
        errors.append("terminal_identity")
    if events[-1].get("event") != "end":
        errors.append("missing_end")
    return sorted(set(errors))
