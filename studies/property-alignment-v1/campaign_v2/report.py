"""Descriptive tables from the unchanged frozen estimate, with explicit denominators."""

from collections import Counter
import csv
import io
import math
from evaluation.safety import mean_evidence
from evaluation_v2.generator import STRATA


def csv_text(rows, fields):
    out = io.StringIO(newline="")
    w = csv.DictWriter(out, fieldnames=fields, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return out.getvalue()


def quantile(values, q):
    values = sorted(values)
    if not values:
        return None
    x = (len(values) - 1) * q
    i = int(x)
    j = min(i + 1, len(values) - 1)
    return values[i] + (values[j] - values[i]) * (x - i)


def timing(values):
    observed = [
        v
        for v in values
        if isinstance(v, (float, int)) and not isinstance(v, bool) and math.isfinite(v)
    ]
    return {
        "observed": len(observed),
        "missing": len(values) - len(observed),
        "minimum_s": min(observed, default=None),
        "median_s": quantile(observed, 0.5),
        "p95_s": quantile(observed, 0.95),
        "maximum_s": max(observed, default=None),
    }


def make_report(audit, analysis, qrows, rows, payloads, selected, execution):
    qualification = []
    primary = []
    secondary = []
    cross = []
    paired = []
    costs = []
    ledger = []
    status_names = sorted({r["candidate"]["status"] for r in rows})
    for s in STRATA:
        qs = [r for r in qrows if r["stratum"] == s]
        rs = [r for r in rows if r["stratum"] == s]
        qc = Counter(r["qualification"]["status"] for r in qs)
        qualification.append(
            {
                "stratum": s,
                "reserve": len(qs),
                "qualified": qc["qualified"],
                "proved_precommand_violation": qc["proved_precommand_violation"],
                "not_certified_by_library": qc["not_certified_by_library"],
                "selected": len(rs),
            }
        )
        c = Counter(r["candidate"]["status"] for r in rs)
        primary.append(
            {
                "stratum": s,
                "selected": len(rs),
                "on_time_decisive_valid": sum(r["primary"]["on_time_decisive_valid"] for r in rs),
                **{status: c[status] for status in status_names},
            }
        )
        for method in ("mean_shortcut", "pairwise_shortcut", "predictive", "barrier"):
            counts = Counter()
            for r in rs:
                if method == "mean_shortcut":
                    outcome = mean_evidence(r)
                elif method == "pairwise_shortcut":
                    v = r["pairwise_shortcut"]
                    outcome = (
                        "not_applicable"
                        if not v["applicable"]
                        else "admits_pairwise"
                        if v["declares_compatible"]
                        else "does_not_admit"
                    )
                else:
                    v = r["native_baselines"].get("methods", {}).get(method)
                    outcome = v["status"] if v is not None else "not_recorded"
                counts[(r["candidate"]["status"], outcome)] += 1
            for (candidate_status, outcome), count in sorted(counts.items()):
                cross.append(
                    {
                        "stratum": s,
                        "method": method,
                        "candidate_status": candidate_status,
                        "comparator_status": outcome,
                        "count": count,
                    }
                )
        for method in ("predictive", "barrier"):
            counts = Counter()
            for r in rs:
                m = r["native_baselines"].get("methods", {}).get(method)
                if m is None:
                    counts[(int(r["primary"]["on_time_decisive_valid"]), "missing")] += 1
                else:
                    counts[(int(r["primary"]["on_time_decisive_valid"]), int(m["protected"]))] += 1
            for a, b in [(0, 0), (0, 1), (1, 0), (1, 1), (0, "missing"), (1, "missing")]:
                paired.append(
                    {
                        "stratum": s,
                        "baseline": method,
                        "candidate_delivered_diagnostic": a,
                        "native_baseline_protected": b,
                        "count": counts[(a, b)],
                    }
                )
        for name, values in [
            ("qualification_algorithm", [r["qualification"].get("wall_s") for r in qs]),
            ("qualification_worker", [r.get("worker_wall_s") for r in qs]),
            ("candidate_policy", [r["candidate"].get("wall_s") for r in rs]),
            ("complete_episode", [r.get("episode_wall_s") for r in rs]),
            ("episode_worker", [r.get("worker_wall_s") for r in rs]),
        ]:
            costs.append({"stratum": s, "measurement": name, **timing(values)})
        for m in ("predictive", "barrier"):
            for cost in ("setup_s", "policy_wall_s"):
                values = [r["native_baselines"].get("methods", {}).get(m, {}).get(cost) for r in rs]
                costs.append({"stratum": s, "measurement": m + "_" + cost, **timing(values)})
        means = Counter(mean_evidence(r) for r in rs)
        pairs = [r for r in rs if r["pairwise_shortcut"]["applicable"]]
        secondary.append(
            {
                "stratum": s,
                "mean_admitted": sum(v for k, v in means.items() if k != "no_admission"),
                "mean_confirmed_false_safe": means["confirmed_false_safe"],
                "mean_unresolved": means["unresolved"],
                "mean_revalidated": means["revalidated"],
                "mean_no_admission": means["no_admission"],
                "pairwise_applicable": len(pairs),
                "pairwise_admitted": sum(
                    r["pairwise_shortcut"]["declares_compatible"] for r in pairs
                ),
                "pairwise_confirmed_false_safe": sum(
                    r["pairwise_shortcut"]["declares_compatible"]
                    and r["candidate"]["status"] == "proved_no_common_held_command"
                    and r["primary"]["valid_certificate"]
                    for r in pairs
                ),
            }
        )
    for r, p in zip(rows, selected, strict=True):
        c = r["candidate"]
        pair = r["pairwise_shortcut"]
        native = r["native_baselines"].get("methods", {})
        ledger.append(
            {
                "stratum": r["stratum"],
                "index": r["index"],
                "case_id": r["case_id"],
                "candidate_status": c["status"],
                "delivered_verified_diagnostic": int(r["primary"]["on_time_decisive_valid"]),
                "policy_wall_s": c.get("wall_s"),
                "episode_wall_s": r.get("episode_wall_s"),
                "action": ";".join(c.get("action") or []),
                "mean_shortcut": mean_evidence(r),
                "pairwise_admission": pair["declares_compatible"]
                if pair["applicable"]
                else "not_applicable",
                "predictive_status": native.get("predictive", {}).get("status", "not_recorded"),
                "barrier_status": native.get("barrier", {}).get("status", "not_recorded"),
                "failure_reason": r.get("failure", {}).get("reason", ""),
            }
        )
    qledger = [
        {
            "stratum": r["stratum"],
            "index": r["index"],
            "case_id": r["case_id"],
            "status": r["qualification"]["status"],
            "eligible": int(r["qualification"]["eligible"]),
            "qualification_wall_s": r["qualification"].get("wall_s"),
            "worker_wall_s": r.get("worker_wall_s"),
        }
        for r in qrows
    ]
    tables = {
        "qualification.csv": csv_text(qualification, list(qualification[0])),
        "primary_by_stratum.csv": csv_text(
            primary, ["stratum", "selected", "on_time_decisive_valid", *status_names]
        ),
        "secondary_by_stratum.csv": csv_text(secondary, list(secondary[0])),
        "matched_status_tables.csv": csv_text(
            cross, ["stratum", "method", "candidate_status", "comparator_status", "count"]
        ),
        "paired_delivery_tables.csv": csv_text(
            paired,
            [
                "stratum",
                "baseline",
                "candidate_delivered_diagnostic",
                "native_baseline_protected",
                "count",
            ],
        ),
        "timing.csv": csv_text(costs, list(costs[0])),
        "selected_case_ledger.csv": csv_text(ledger, list(ledger[0])),
        "qualification_ledger.csv": csv_text(qledger, list(qledger[0])),
    }
    failures = [r for r in ledger if not r["delivered_verified_diagnostic"]]
    tables["unsuccessful_delivery_ledger.csv"] = csv_text(failures, list(ledger[0]))
    summary = {
        "schema": "sal-replacement-results-summary/1",
        "evaluation_id": analysis["replacement_evaluation_id"],
        "campaign_complete": analysis["campaign_complete"],
        "validity_claim_gate_passed": analysis["validity_claim_gate_passed"],
        "qualification": qualification,
        "primary": primary,
        "secondary": secondary,
        "timing": costs,
        "primary_estimate": analysis["balanced_coverage"],
        "on_time_verified_diagnostics": analysis["on_time_decisive_valid"],
        "candidate_statuses": analysis["candidate_statuses"],
        "invalid_definite_certificates": analysis["invalid_definite_certificates"],
        "elapsed_campaign_s": execution["elapsed_s"],
        "frozen_analysis_unchanged": True,
        "inference_scope": analysis["balanced_coverage"]["target"],
        "superiority_test_performed": False,
        "performance_success_threshold_prespecified": False,
        "utility_collision_hold_abort_measured": False,
        "physical_validation": False,
        "protected_inputs": len(selected),
        "qualification_reserve": len(payloads),
        "quantile_definition": "Linear interpolation at (n-1)*q of the sorted observed values",
        "claim_status": {
            "coverage": "estimated"
            if analysis["validity_claim_gate_passed"]
            else "validity_gate_failed",
            "complete_recovery": "not_evaluated",
            "controller_superiority": "not_tested",
            "physical_safety": "not_evaluated",
        },
        "limitations": [
            "Single Mac run; conditional-mean interval is not independent hardware reliability.",
            "Finite common prefixes and HCW obstructions, without a mission-recovery endpoint.",
            "Native baselines retain different information representations and continuation obligations; matched tables do not establish superiority.",
            "No new numerical replay beyond the predeclared in-episode checks; audit checks recorded structure and arithmetic.",
            "The failed original campaign remains invalid and excluded.",
        ],
    }
    return summary, tables
