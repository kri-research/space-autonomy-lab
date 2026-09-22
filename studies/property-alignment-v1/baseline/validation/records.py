"""Strict read-only aggregation of historical episode records.

This module never executes spacecraft propagation or changes a frozen endpoint.
New common-property witnesses are placed in separate fields.
"""

from __future__ import annotations
import math
from collections import Counter, defaultdict
from typing import Any

ARMS = ("primary_reference", "independent_monitor_gate")
ENDPOINTS = ("physical_collision", "physical_keep_out_entry", "physical_corridor_departure")
PRIMARY = {
    "E004": ("P04_primary_navigation_bias", "P05_primary_navigation_dropout"),
    "E005": ("T03_primary_navigation_bias", "T04_primary_navigation_dropout"),
}
EXPECTED = {
    "E004": {
        "P00_nominal_feasibility": 64,
        "P04_primary_navigation_bias": 534,
        "P05_primary_navigation_dropout": 534,
        "P06_monitor_navigation_bias": 64,
        "P07_monitor_logic_false_trip": 64,
        "P08_shared_navigation_bias": 64,
        "P09_actuation_degradation": 64,
        "P10_disturbance_burst": 64,
    },
    "E005": {"T03_primary_navigation_bias": 534, "T04_primary_navigation_dropout": 534},
}


def nonnegative_integer(value: Any) -> bool:
    return type(value) is int and value >= 0


def aggregate(study: str, rows: list[dict], expected_counts: dict[str, int] | None = None) -> dict:
    """Validate membership and return historical counts and separate diagnostics."""
    if study not in PRIMARY:
        raise ValueError("Unknown study")
    expected = EXPECTED[study] if expected_counts is None else expected_counts
    if len(rows) != 2 * sum(expected.values()):
        raise ValueError("Episode count differs")
    cells = {}
    groups = defaultdict(list)
    root_cases = {}
    for r in rows:
        if not isinstance(r, dict):
            raise ValueError("Expected row object")
        if r.get("case_id") not in expected or r.get("configuration_id") not in ARMS:
            raise ValueError("Unexpected case or arm")
        for field in (*ENDPOINTS, "hold_acquired", "infrastructure_failure"):
            if type(r.get(field)) is not bool:
                raise ValueError(f"Non-Boolean {field}")
        if r["infrastructure_failure"]:
            raise ValueError("Infrastructure-invalid row")
        numerical = "numerical_valid" if study == "E004" else "nonlinear_truth_numerical_valid"
        if r.get(numerical) is not True or r.get("attempt_status") != "valid":
            raise ValueError("Numerically invalid or incomplete attempt")
        for field in [
            "minimum_separation_m",
            "minimum_covariance_eigenvalue",
            "maximum_covariance_trace",
        ]:
            value = r.get(field)
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError(f"Nonfinite or invalid {field}")
        if r["minimum_separation_m"] < 0:
            raise ValueError("Negative separation")
        if r["minimum_covariance_eigenvalue"] < -1e-12 or r["maximum_covariance_trace"] >= 1e6:
            raise ValueError("Covariance validity limit")
        if r["physical_collision"] and not r["physical_keep_out_entry"]:
            raise ValueError("Collision / keep-out nesting differs")
        if not nonnegative_integer(r.get("replicate")):
            raise ValueError("Invalid replicate")
        key = (r.get("root_seed_id"), r["configuration_id"])
        if not isinstance(key[0], str) or not key[0] or key in cells:
            raise ValueError("Missing or duplicated cell")
        if key[0] in root_cases and root_cases[key[0]] != r["case_id"]:
            raise ValueError("Root used in two cases")
        root_cases[key[0]] = r["case_id"]
        cells[key] = r
        n = r.get("monitor_override_commands")
        reasons = r.get("monitor_reason_counts")
        if not nonnegative_integer(n) or n > 300:
            raise ValueError("Invalid override count")
        if not isinstance(reasons, dict) or any(
            not nonnegative_integer(v) for v in reasons.values()
        ):
            raise ValueError("Invalid reason counts")
        if sum(reasons.values()) != n:
            raise ValueError("Override / reason mismatch")
        if r["configuration_id"] == ARMS[0] and n:
            raise ValueError("Reference cannot override")
        for field in ["primary_disposition_counts", "monitor_disposition_counts"]:
            counts = r.get(field)
            if (
                not isinstance(counts, dict)
                or any(not nonnegative_integer(v) for v in counts.values())
                or sum(counts.values()) != 301
            ):
                raise ValueError("Disposition count mismatch")
        groups[(r["case_id"], r["configuration_id"])].append(r)
    summary = []
    frequencies = []
    witnesses = []
    pair_tables = []
    equality = []
    for case, n in expected.items():
        for arm in ARMS:
            group = groups[(case, arm)]
            if len(group) != n or {r["replicate"] for r in group} != set(range(n)):
                raise ValueError("Case/arm or replicate membership differs")
            freq = Counter(r["monitor_override_commands"] for r in group)
            reasons = sum((Counter(r["monitor_reason_counts"]) for r in group), Counter())
            summary.append(
                {
                    "study": study,
                    "case": case,
                    "arm": arm,
                    "role": "primary" if case in PRIMARY[study] else "descriptive",
                    "episodes": len(group),
                    **{f: sum(r[f] for r in group) for f in (*ENDPOINTS, "hold_acquired")},
                    "historical_composite": sum(any(r[f] for f in ENDPOINTS) for r in group),
                    "closed_union_witness_count": sum(
                        r["minimum_separation_m"] < 27 for r in group
                    ),
                    "minimum_episode_minimum_m": min(r["minimum_separation_m"] for r in group),
                    "maximum_episode_minimum_m": max(r["minimum_separation_m"] for r in group),
                    "episodes_with_override": sum(
                        r["monitor_override_commands"] > 0 for r in group
                    ),
                    "override_decisions": sum(r["monitor_override_commands"] for r in group),
                    "quality_reason_decisions": reasons["ESTIMATOR_QUALITY"],
                    "geometry_reason_decisions": reasons["UNCERTAINTY_AWARE_GEOMETRY"],
                }
            )
            for k, count in sorted(freq.items()):
                frequencies.append(
                    dict(study=study, case=case, arm=arm, override_count=k, episodes=count)
                )
            for r in sorted(group, key=lambda q: q["replicate"]):
                witnesses.append(
                    dict(
                        study=study,
                        case=case,
                        arm=arm,
                        root_seed_id=r["root_seed_id"],
                        replicate=r["replicate"],
                        historical_corridor_flag=r["physical_corridor_departure"],
                        historical_composite=any(r[f] for f in ENDPOINTS),
                        minimum_separation_m=r["minimum_separation_m"],
                        retrospective_closed_union_witness=r["minimum_separation_m"] < 27,
                        witness_margin_m=27 - r["minimum_separation_m"],
                        override_decisions=r["monitor_override_commands"],
                        quality_reason_decisions=r["monitor_reason_counts"].get(
                            "ESTIMATOR_QUALITY", 0
                        ),
                        geometry_reason_decisions=r["monitor_reason_counts"].get(
                            "UNCERTAINTY_AWARE_GEOMETRY", 0
                        ),
                        trace_digest=r["trace_digest"],
                        scenario_hash=r["scenario_hash"],
                    )
                )
    paired = Counter()
    eq = Counter()
    primary_pairs = 0
    for root, case in root_cases.items():
        if any((root, arm) not in cells for arm in ARMS):
            raise ValueError("Incomplete pair")
        r, g = (cells[(root, arm)] for arm in ARMS)
        if r["replicate"] != g["replicate"]:
            raise ValueError("Paired replicate mismatch")
        for field in ["scenario_hash", "stream_hashes", "controller_identity"]:
            if r.get(field) != g.get(field):
                raise ValueError(f"Paired {field} mismatch")
        if case not in PRIMARY[study]:
            continue
        primary_pairs += 1
        a, b = (int(any(q[f] for f in ENDPOINTS)) for q in [r, g])
        paired[f"n{a}{b}"] += 1
        for field in [
            "trace_digest",
            "minimum_separation_m",
            "final_state",
            "final_truth_relative_state",
            "maximum_admissible_position_excess_m",
        ]:
            if field in r and field in g:
                eq[field] += int(r[field] == g[field])
    pair_tables.append(
        dict(
            study=study,
            paired_roots=primary_pairs,
            **{f: paired[f] for f in ["n00", "n10", "n01", "n11"]},
        )
    )
    equality.append(dict(study=study, paired_roots=primary_pairs, **eq))
    return dict(
        summary=summary,
        frequencies=frequencies,
        witnesses=witnesses,
        pair_tables=pair_tables,
        equality=equality,
    )
