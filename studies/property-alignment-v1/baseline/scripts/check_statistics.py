#!/usr/bin/env python3
"""Check the published paired-test algebra and planning calculation, without simulation."""

from __future__ import annotations
import argparse
import json
import math
from pathlib import Path
from scipy.stats import binom


def design_check() -> dict:
    alpha, alternative, target = 0.025, 0.55, 0.90
    candidates = []
    for n in range(2, 1070, 2):
        critical = int(binom.isf(alpha, n, 0.5)) + 1
        minimum_effect_critical = math.ceil(0.525 * n - 1e-12)
        threshold = max(critical, minimum_effect_critical)
        candidates.append(
            {
                "n": n,
                "critical_beneficial": critical,
                "achieved_alpha": float(binom.sf(critical - 1, n, 0.5)),
                "planning_power": float(binom.sf(critical - 1, n, alternative)),
                "critical_with_effect_floor": threshold,
                "power_with_effect_floor": float(binom.sf(threshold - 1, n, alternative)),
            }
        )
    selected = next(c for c in candidates if c["planning_power"] >= target)
    assert selected["n"] == 1068 and selected["critical_beneficial"] == 567
    assert all(c["planning_power"] < target for c in candidates if c["n"] < 1068)
    examples = []
    for n00, n10, n01, n11 in [(1068, 0, 0, 0), (0, 0, 0, 1068)]:
        n, m = n00 + n10 + n01 + n11, n10 + n01
        p = float(binom.sf(n10 - 1, m, 0.5)) if m else 1.0
        delta = (n01 - n10) / n
        examples.append(
            {
                "n00": n00,
                "n10": n10,
                "n01": n01,
                "n11": n11,
                "n": n,
                "risk_difference": delta,
                "p": p,
                "reference_fraction": (n10 + n11) / n,
                "gate_fraction": (n01 + n11) / n,
            }
        )
    return {
        "method": "Deterministic binomial tail calculations, not a new experiment.",
        "planning_assumption": "All pairs discordant, beneficial probability 0.55.",
        "selected": selected,
        "previous_even": candidates[-2],
        "all_smaller_even_candidates_below_target": True,
        "endpoint_examples": examples,
        "claim_limit": "Checks this planning construction only; no observed-power or universal heterogeneity claim.",
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    result = design_check()
    text = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
