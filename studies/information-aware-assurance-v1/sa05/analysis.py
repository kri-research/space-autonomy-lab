"""Frozen paired analysis. One latent episode is the unit, never a packet/time step."""

import math
from collections import Counter
from statistics import mean, median

from scipy.stats import binomtest

from .design import METHODS, STRATA


def exact_discordance_p(wins, losses):
    """Two-sided exact conditional paired binary test, independently enumerable."""
    total = wins + losses
    return (
        min(1.0, 2 * sum(math.comb(total, k) for k in range(min(wins, losses) + 1)) / 2**total)
        if total
        else 1.0
    )


def holm(values):
    result = [None] * len(values)
    ordered = sorted((v, i) for i, v in enumerate(values) if v is not None)
    # The family size remains predeclared even if missingness disables a test.
    previous = 0.0
    for rank, (value, i) in enumerate(ordered):
        previous = max(previous, min(1.0, value * (len(values) - rank)))
        result[i] = previous
    return result


def binary_pair(a, b, alpha=0.0125):
    if len(a) != len(b) or not a:
        raise ValueError("Nonempty complete paired unit lists required")
    if any(type(v) not in (bool, type(None)) for v in (*a, *b)):
        raise ValueError("Boolean outcomes or explicitly missing")
    missing = sum(x is None or y is None for x, y in zip(a, b, strict=True))
    lower = sum(
        (0 if x is None else x) - (1 if y is None else y) for x, y in zip(a, b, strict=True)
    ) / len(a)
    upper = sum(
        (1 if x is None else x) - (0 if y is None else y) for x, y in zip(a, b, strict=True)
    ) / len(a)
    wins = sum(x is True and y is False for x, y in zip(a, b, strict=True))
    losses = sum(x is False and y is True for x, y in zip(a, b, strict=True))
    # Hoeffding for independent units with signed outcomes in [-1,1].
    halfwidth = math.sqrt(2 * math.log(2 / alpha) / len(a))
    return dict(
        n=len(a),
        missing_pairs=missing,
        wins=wins,
        losses=losses,
        risk_difference=None if missing else lower,
        missing_data_identification_interval=[lower, upper],
        conservative_simultaneous_interval=[
            max(-1.0, lower - halfwidth),
            min(1.0, upper + halfwidth),
        ],
        exact_p=None if missing else exact_discordance_p(wins, losses),
        interval_alpha=alpha,
    )


def rate_interval(success, n):
    interval = binomtest(success, n).proportion_ci(confidence_level=0.95, method="exact")
    return [float(interval.low), float(interval.high)]


def summarize(cases, rows):
    expected = {(c["unit"], m) for c in cases for m in METHODS}
    keys = [(r["unit"], r["method"]) for r in rows]
    if len(keys) != len(set(keys)) or set(keys) != expected:
        raise ValueError("Incomplete, duplicate or foreign unit-method membership")
    table = {key: r for key, r in zip(keys, rows, strict=True)}
    absolute = []
    for stratum in STRATA:
        units = [c["unit"] for c in cases if c["stratum"] == stratum]
        for method in METHODS:
            group = [table[u, method] for u in units]
            complete = [r for r in group if r["status"] == "completed"]
            n = len(group)
            if not n:
                continue
            successes = sum(r["mission_completion"] for r in complete)
            acquisitions = sum(r["acquired_goal"] for r in complete)
            absolute.append(
                dict(
                    stratum=stratum,
                    method=method,
                    scheduled=n,
                    completed=len(complete),
                    missing=n - len(complete),
                    constraints=dict(Counter(r["constraint_status"] for r in complete)),
                    mission_completion=successes,
                    acquired_goal=acquisitions,
                    initially_eligible=sum(r["initially_goal_eligible"] for r in complete),
                    acquisition_rate_exact95=rate_interval(acquisitions, n)
                    if len(complete) == n
                    else None,
                    requests=sum(r["observation_requests"] for r in complete),
                    nonzero_interventions=sum(r["nonzero_intervention"] for r in complete),
                    unsafe_admissions=sum(r["unsafe_admission_observed"] for r in complete),
                    exclusions=sum(r["nonempty_information_exclusion"] for r in complete),
                    unresolved=sum(r["unresolved_decision"] for r in complete),
                    retained_protective_continuations=sum(
                        r["protective_continuation_used"] for r in complete
                    ),
                    modeled_late_planning=sum(r["planner_clock_late"] for r in complete),
                    modeled_late_checking=sum(r["checker_clock_late"] for r in complete),
                    missed_application=sum(r["missed_application_window"] for r in complete),
                    mean_modeled_energy_mj=mean(r["modeled_energy_mj"] for r in complete)
                    if complete
                    else None,
                    median_potential_change_m2=median(
                        r["task_potential_change_m2"] for r in complete
                    )
                    if complete
                    else None,
                    native_scope="finite_4.2_second_manoeuvre_numerical_model",
                )
            )
    primary = []
    for s in STRATA[:2]:
        units = [c["unit"] for c in cases if c["stratum"] == s]
        if not units:
            continue
        for baseline in ("fixed_range", "uncertainty_triggered"):
            candidate = [table[u, "decision_aware"] for u in units]
            controls = [table[u, baseline] for u in units]

            def outcome(r):
                return r["acquired_goal"] if r["status"] == "completed" else None

            comparison = binary_pair(list(map(outcome, candidate)), list(map(outcome, controls)))
            comparison.update(
                stratum=s,
                candidate="decision_aware",
                baseline=baseline,
                outcome="acquired_goal_with_numerical_containment",
            )
            primary.append(comparison)
    for row, p in zip(primary, holm([r["exact_p"] for r in primary]), strict=True):
        row["holm_p"] = p
    return dict(
        schema="iaa-sa05-analysis/1",
        units=len(cases),
        scheduled=len(expected),
        completed=sum(r["status"] == "completed" for r in rows),
        unit_definition="paired initial state and exogenous latent conditions",
        absolute=absolute,
        primary=primary,
        energy_measured=False,
        timing_claim="simulated phase times; host durations reported separately",
        operational_reliability_claim=False,
    )


def host_summary(timings):
    groups = []
    for method in METHODS:
        group = [r for r in timings if r["method"] == method and r.get("planner_ns") is not None]
        groups.append(
            dict(
                method=method,
                n=len(group),
                planner_over_50ms=sum(r["planner_over_50ms"] for r in group),
                checker_over_50ms=sum(r["checker_over_50ms"] for r in group),
                planner_median_ms=median(r["planner_ns"] / 1e6 for r in group) if group else None,
                planner_max_ms=max((r["planner_ns"] / 1e6 for r in group), default=None),
                checker_max_ms=max((r["checker_ns"] / 1e6 for r in group), default=None),
                process_peak_rss_max_bytes=max((r["peak_rss_bytes"] for r in group), default=None),
            )
        )
    return dict(
        scope="actual isolated-process host measurements, not target timing or WCET", groups=groups
    )
