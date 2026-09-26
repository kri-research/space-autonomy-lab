"""One-observation decision tree with complete bounded-outcome checks."""

from fractions import Fraction as Q

from iaa.types import ObservationPacket, encode, millis, rational
from sa02.model import Budget, ResourceLimit

from .forecast import carry, choose_action, hull, outcome_partition, waiting_check

METHODS = ("fixed_range", "fixed_bearing", "uncertainty_triggered", "decision_aware")
SENSOR_COST = {"range": Q(1, 5), "bearing": Q(3, 10), None: Q(0)}


def build_option(context, channel, budget):
    if channel not in (None, "range", "bearing"):
        raise ValueError("Unsupported observation channel")
    t = context.timing
    result = dict(
        schema="iaa-sa03-tree/1",
        context_sha256=context.identity(),
        channel=channel,
        protected_until_ms=t.end_ms,
        protected_from_ms=t.now_ms,
        all_outcome_protection=False,
        all_reading_useful=False,
        universal_mission_completion=False,
        negative_certificate=False,
    )
    if not context.usable:
        return result | dict(
            status="invalid_assumptions",
            reason=(
                "assumption_flag_false"
                if not context.assumptions_supported
                else context.estimate.status
            ),
        )
    if not waiting_check(context, budget):
        return result | dict(status="unresolved", reason="unsafe_or_unresolved_wait")
    at_apply, _ = carry(context.estimate.cells, context.queue(), t.now_ms, t.apply_ms, budget)
    fallback, fallback_attempts = choose_action(at_apply, budget)
    result.update(
        wait_checked=True,
        no_observation=fallback,
        no_observation_attempts=fallback_attempts,
        no_observation_hull=hull(at_apply),
    )
    if fallback is None:
        return result | dict(status="unresolved", reason="no_supported_missing_observation_branch")
    if channel is None:
        return result | dict(
            status="checked_action",
            all_outcome_protection=True,
            all_reading_useful=fallback["useful"],
            leaves=(),
        )
    if t.ready(channel) > t.apply_ms:
        return result | dict(status="late", reason="observation_processing_misses_application")
    domain, leaves, nodes = outcome_partition(context, channel, budget)
    checked = []
    for leaf in leaves:
        if not leaf["cells"]:
            checked.append(
                dict(reading=leaf["reading"], status=leaf["status"], retained_cells=0, result=None)
            )
            continue
        command, attempts = choose_action(leaf["cells"], budget)
        checked.append(
            dict(
                reading=leaf["reading"],
                status=leaf["status"],
                retained_cells=len(leaf["cells"]),
                result=command,
                application_hull=hull(leaf["cells"]),
                attempts=attempts,
            )
        )
    live = [r for r in checked if r["retained_cells"]]
    protected = bool(live) and all(r["result"] is not None for r in live)
    useful = protected and all(r["result"]["useful"] for r in live)
    result.update(
        domain=domain,
        leaves=tuple(checked),
        nodes=nodes,
        all_outcome_protection=protected,
        all_reading_useful=useful,
        status="checked_tree" if protected else "unresolved",
        reason="all_readings_and_missing_branch_checked"
        if protected
        else "at_least_one_branch_lacks_supported_continuation",
    )
    return result


def cost(operations, channel):
    # Work accounting model, not processor or sensor energy measurement.
    return Q(5) + Q(operations, 1000) + SENSOR_COST[channel] + (Q(5) if channel else Q(0))


def decide(context, method):
    if method not in METHODS:
        raise ValueError("Unknown comparator")
    budget = Budget(context.max_operations)
    candidates = []
    selected = None
    status = "unresolved"
    try:
        if context.resource_mj < 5:
            raise ResourceLimit("Insufficient modeled budget to start decision")
        base = build_option(context, None, budget)
        candidates.append(base)
        if not base["all_outcome_protection"]:
            status = base["status"]
        elif method == "decision_aware" and base["all_reading_useful"]:
            selected = base
        else:
            if method.startswith("fixed_"):
                channels = (method.removeprefix("fixed_"),)
            elif method == "uncertainty_triggered":
                box = context.estimate.hull()
                widths = [b - a for a, b in zip(box.lower[:2], box.upper[:2], strict=True)]
                channels = (
                    (("bearing" if widths[0] > widths[1] else "range"),)
                    if max(widths) > Q(1, 4)
                    else ()
                )
            else:
                channels = ("range", "bearing")
            for channel in channels:
                candidates.append(build_option(context, channel, budget))
            choices = [
                r
                for r in candidates[1:]
                if r["all_outcome_protection"]
                and (r["all_reading_useful"] or method != "decision_aware")
            ]
            selected = min(choices, key=lambda r: SENSOR_COST[r["channel"]]) if choices else base
        if selected is not None:
            status = selected["status"]
            if cost(budget.used, selected["channel"]) > context.resource_mj:
                status = "resource_exhausted"
                selected = None
    except ResourceLimit as exc:
        status = "resource_exhausted"
        candidates.append(dict(status=status, reason=str(exc)))
        selected = None
    except (ValueError, KeyError, TypeError, ArithmeticError) as exc:
        status = "unresolved_numerics_or_input"
        candidates.append(dict(status=status, reason=type(exc).__name__ + ":" + str(exc)))
        selected = None
    return dict(
        schema="iaa-sa03-policy/1",
        method=method,
        status=status,
        context_sha256=context.identity(),
        certificate=selected,
        candidates=tuple(candidates),
        operations=budget.used,
        modeled_cost_mj=(
            Q(0)
            if context.resource_mj < 5
            else cost(budget.used, selected["channel"] if selected else None)
        ),
        actual_realtime_feasibility=False,
        full_recovery=False,
    )


def verify_tree(context, certificate):
    """Recompute the selected complete tree, never trust a Boolean certificate flag."""
    if not isinstance(certificate, dict) or certificate.get("context_sha256") != context.identity():
        return False
    try:
        expected = build_option(context, certificate["channel"], Budget(context.max_operations))
        return expected["all_outcome_protection"] and encode(expected) == encode(certificate)
    except (ValueError, KeyError, TypeError, ArithmeticError, ResourceLimit):
        return False


def dispatch(context, policy, packets, now_ms):
    """Trusted simulated dispatcher. A selected branch never extends application time."""
    millis(now_ms)
    if now_ms != context.timing.apply_ms:
        return dict(
            status="late" if now_ms > context.timing.apply_ms else "not_yet_due",
            action=(Q(0), Q(0)),
            credited=False,
            useful=False,
        )
    cert = policy.get("certificate")
    if (
        cert is None
        or not verify_tree(context, cert)
        or policy.get("context_sha256") != context.identity()
        or not cert.get("all_outcome_protection")
        or policy.get("status") not in ("checked_tree", "checked_action")
    ):
        return dict(
            status="unverified_or_unresolved", action=(Q(0), Q(0)), credited=False, useful=False
        )
    chosen = cert["no_observation"]
    reason = "no_observation_action"
    selected_hull = cert["no_observation_hull"]
    selected_reading = None
    channel = cert["channel"]
    if channel:
        expected_id = "sa03-" + context.identity()[:16] + "-" + channel
        matching = [
            p for p in packets if isinstance(p, ObservationPacket) and p.packet_id == expected_id
        ]
        if len(set(encode(p) for p in matching)) > 1:
            matching = []
            reason = "conflicting_receipt_fallback"
        if matching:
            p = matching[0]
            t = context.timing
            delay = t.range_delay_ms if channel == "range" else t.bearing_delay_ms
            if (
                p.channel == channel
                and p.acquired_ms == t.acquire_ms
                and p.timestamp_uncertainty_ms <= t.timestamp_ms
                and p.available_ms <= t.acquire_ms + delay
                and p.available_ms + t.processing_ms <= now_ms
            ):
                reading = rational(p.value)
                found = [leaf for leaf in cert["leaves"] if leaf["reading"].contains(reading)]
                # Boundaries are shared. Every selected live branch is separately checked.
                live = [leaf for leaf in found if leaf["result"] is not None]
                if live:
                    chosen = live[0]["result"]
                    selected_hull = live[0]["application_hull"]
                    selected_reading = live[0]["reading"]
                    reason = "observation_contingent_action"
                else:
                    reason = "outside_predicted_support_fallback"
            else:
                reason = "late_or_invalid_receipt_fallback"
    return dict(
        status=reason,
        action=chosen["action"],
        credited=True,
        useful=chosen["useful"],
        protected_until_ms=cert["protected_until_ms"],
        checked_application_hull=selected_hull,
        selected_reading_interval=selected_reading,
        full_recovery=False,
    )
