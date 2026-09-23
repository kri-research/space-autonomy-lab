"""Complete within-case developmental contrasts; no population significance tests."""

from pathlib import Path
from collections import Counter
import argparse
import json
from .experiment import save_csv
from .io import sha, save_json, manifest, verify_seal


def verify_delivery(root):
    root = Path(root).resolve()
    catalog = json.loads((root / "manifest.json").read_text())
    for relative, expected in catalog.items():
        path = root / relative
        if not path.resolve().is_relative_to(root) or path.is_symlink() or sha(path) != expected:
            raise ValueError("Artifact identity mismatch: " + relative)
    p = json.loads((root / "protocol.json").read_text())
    expected = {(c["id"], m, a) for c in p["cases"] for m in p["plants"] for a in p["arms"]}
    rows = [json.loads(f.read_text()) for f in sorted((root / "cells").glob("*/summary.json"))]
    if {(r["case"], r["plant"], r["arm"]) for r in rows} != expected or len(rows) != len(expected):
        raise ValueError("Incomplete or duplicated matrix")
    for r in rows:
        if r["execution_status"] != "complete" or r["commands"] != 300 or r["states"] != 1201:
            raise ValueError("Incomplete selected attempt")
        if r["adjudication"].get("simulator_agreement") != "within_predeclared_comparison_limit":
            raise ValueError("Numerical comparison prerequisite failed; retain affected result")
    for c in p["cases"]:
        group = [r for r in rows if r["case"] == c["id"]]
        if (
            len({r["controller_identity"] for r in group}) != 1
            or len({json.dumps(r["innovation_sha256"], sort_keys=True) for r in group}) != 1
        ):
            raise ValueError("Pairing violated")
    return p, rows


def scalar(r):
    adj = r["adjudication"]
    bracket = adj.get("first_exit_bracket_s")
    radius = adj.get("minimum_separation_enclosure_m")
    return {
        "case": r["case"],
        "information": r["information"],
        "role": r["case_role"],
        "plant": r["plant"],
        "arm": r["arm"],
        "physical_status": r["physical_status"],
        "hold": adj.get("hold_acquired", "unresolved"),
        "overrides": r["overrides"],
        "changed_commands": r["changed_commands"],
        "geometry_checks": r["geometry_checks"],
        "geometry_rejections": r["geometry_rejections"],
        "numerical_rejections": r["numerically_unresolved_decisions"],
        "first_exit_lower_s": None if bracket is None else bracket[0],
        "first_exit_upper_s": None if bracket is None else bracket[1],
        "min_separation_lower_m": None if radius is None else radius[0],
        "min_separation_upper_m": None if radius is None else radius[1],
        "sampled_minimum_m": r["sampled_minimum_separation_m"],
        "control_effort_mps": r["control_effort_integral_mps"],
        "decision_cpu_s": r["decision_cpu_total_s"],
        "decision_wall_max_s": r["decision_wall_max_s"],
        "fault_packet_dispositions": json.dumps(r["fault_packet_dispositions"], sort_keys=True),
        "ambiguous_intervals": adj.get("ambiguous_intervals"),
    }


def contrast(r, g, label):
    fields = [
        "overrides",
        "changed_commands",
        "geometry_checks",
        "geometry_rejections",
        "control_effort_integral_mps",
        "sampled_minimum_separation_m",
    ]
    return {
        "case": r["case"],
        "plant": r["plant"],
        "contrast": label,
        "reference_arm": r["arm"],
        "comparison_arm": g["arm"],
        "reference_physical": r["physical_status"],
        "comparison_physical": g["physical_status"],
        "same_motion": r["motion_sha256"] == g["motion_sha256"],
        "same_selected_commands": r["selected_command_sha256"] == g["selected_command_sha256"],
        "same_applied_commands": r["applied_command_sha256"] == g["applied_command_sha256"],
        **{k + "_difference": g[k] - r[k] for k in fields},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execution", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.execution.resolve()
    verify_seal()
    p, rows = verify_delivery(root)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    table = [scalar(r) for r in rows]
    save_csv(output / "comparison.csv", list(table[0]), [list(r.values()) for r in table])
    comparisons = []
    for case in p["cases"]:
        for plant in p["plants"]:
            q = {r["arm"]: r for r in rows if r["case"] == case["id"] and r["plant"] == plant}
            comparisons.extend(
                [
                    contrast(q["controlled_in_band"], q["controlled_union"], "predicate_only"),
                    contrast(
                        q["original_gate"],
                        q["controlled_in_band"],
                        "numerical_search_and_unresolved_policy",
                    ),
                    contrast(q["no_gate"], q["original_gate"], "original_additional_gate"),
                ]
            )
    save_json(output / "contrasts.json", comparisons)
    core = [c for c in comparisons if c["contrast"] == "predicate_only"]
    interactions = []
    for case in p["cases"]:
        q = {r["plant"]: r for r in core if r["case"] == case["id"]}
        interactions.append(
            {
                "case": case["id"],
                **{
                    k + "_plant_interaction": q["nonlinear"][k] - q["hcw"][k]
                    for k in q["hcw"]
                    if k.endswith("_difference")
                },
            }
        )
    save_json(output / "plant_predicate_interactions.json", interactions)
    qualification = [
        json.loads(f.read_text()) for f in sorted((root / "qualification").glob("*/result.json"))
    ]
    counts = {
        "total_cells": len(rows),
        "completed_command_decisions": sum(r["commands"] for r in rows),
        "state_observations": sum(r["states"] for r in rows),
        "packet_opportunities": sum(r["packet_opportunities"] for r in rows),
        "status_by_role": {
            role: dict(Counter(r["physical_status"] for r in rows if r["case_role"] == role))
            for role in sorted({r["case_role"] for r in rows})
        },
        "qualification_statuses": dict(
            Counter(q["finite_horizon_recoverability"] for q in qualification)
        ),
    }
    result = {
        "schema": "sal-causal-analysis/1",
        "study_kind": "selected_developmental_mechanistic_cases",
        "protocol_sha256": sha(root / "protocol.json"),
        "execution_manifest_sha256": sha(root / "manifest.json"),
        "counts": counts,
        "qualification": qualification,
        "predicate_contrasts": core,
        "same_motion_core_pairs": sum(c["same_motion"] for c in core),
        "changed_motion_core_pairs": sum(not c["same_motion"] for c in core),
        "historical_outcomes_modified": False,
        "task05_executed": False,
        "inferential_tests_performed": False,
        "physical_validation": False,
        "qualification_limits": "Ideal known-state finite-horizon fixed-input witnesses only; estimator cases have no robust/common-information recovery certificate.",
        "limits": [
            "Source/schedules establish factor isolation; no sampled node is an independent trial.",
            "Original versus controlled-inband includes validated numerical search and its explicit unresolved/rejection policy.",
            "Offline certification concerns intended mathematical ODE under recorded inputs, not exact feedback equivalence.",
            "No operational prevalence, global model-irrelevance claim or historical event-by-event causal reconstruction.",
        ],
    }
    save_json(output / "results.json", result)
    lines = [
        "# Controlled predicate comparison",
        "",
        "A prospectively declared developmental mechanistic study. Historical campaigns, flags and decisions are unchanged. The protocol and source were sealed before these new selected outcomes.",
        "",
        "The matrix contains 56 cells across four arms, two plants and seven state/information contexts. Six additional ideal fixed-input feasibility witnesses qualify the main admissible cases. All attempts are retained.",
        "",
        "## Isolation",
        "",
        "The controlled arms differ only in the position predicate. They share one-second HCW interval prediction, numerical search and resolution, covariance inflation, input bounds, controller, fallback and information. An unresolved prediction rejects without certifying the fallback. The original gate is unchanged; the no-gate reference retains estimator safeguards.",
        "",
        "## Observations",
        "",
        f"Recorded motion is identical in {result['same_motion_core_pairs']} of {len(core)} predicate-only pairs and differs in {result['changed_motion_core_pairs']}. These counts describe selected cases, not a population.",
        "",
        "| Context | Plant | In-band overrides | Aligned overrides | Same motion | In-band / aligned outcome |",
        "| --- | --- | ---: | ---: | --- | --- |",
    ]
    by = {(r["case"], r["plant"], r["arm"]): r for r in rows}
    for c in core:
        r = by[(c["case"], c["plant"], "controlled_in_band")]
        g = by[(c["case"], c["plant"], "controlled_union")]
        lines.append(
            f"| {c['case']} | {c['plant']} | {r['overrides']} | {g['overrides']} | {c['same_motion']} | {r['physical_status']} / {g['physical_status']} |"
        )
    lines += [
        "",
        "Complete commands, packets and trajectories distinguish injection from acceptance, geometry checks from other branches, overrides from changed commands, and unresolved intervals from safety. All contrasts and plant/predicate interactions, including nulls, are supplied.",
        "",
        "## Interpretation",
        "",
        "With ideal equal primary/monitor snapshots, fallback evaluates exactly the same LQR proposal. Rejection can change logs without changing control. This identity is a separate unit-tested implementation property, not a claim about a different fallback or longer horizon.",
        "",
        "The outward-moving boundary state is analytically unrecoverable for containment and stays a labelled control. Qualification shows only finite-horizon ideal known-state feasibility; it is not a robust certificate for noisy estimator cases. Numerical frame/propagation differences are recorded separately from interval error bounds.",
        "",
        "This developmental result is retained for subsequent baseline development. These outcomes cannot later be described as held-out evaluation data.",
    ]
    (output / "RESULTS.md").write_text(chr(10).join(lines) + chr(10))
    manifest(output)
    print(json.dumps(counts, indent=2))


if __name__ == "__main__":
    main()
