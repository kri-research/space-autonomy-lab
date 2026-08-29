# Experiment 002c numerical corrective amendment

_Fixed-command numerical validation after the frozen Experiment 002b failure_

---

> 📌 **Historical boundary:** Experiment 002 and Experiment 002b protocols, freezes, artifacts,
> results, and decisions remain unchanged. Experiment 002c has disjoint seeds, its own freeze, and
> its own results.

## 🎯 Corrective scope

Experiment 002c addresses the numerical blocker diagnosed after Experiment 002b. The diagnosis found
an independent-reference defect at acceleration-zero kinks, an unrealistically strict universal
unit-mixing threshold, and a separate production defect that computed terminal interval extrema past
the actual collision time. Smooth production state propagation was accurate, depletion/reset
conditioning amplified small propellant errors, and no controller defect was indicated.

The amendment makes two implementation corrections:

- Production collision-terminated interval extrema stop at the collision time
- The independent numerical reference terminates and restarts integration at achieved-acceleration
  zero crossings before integrating propellant in smooth known-sign phases

No dynamics or controller redesign is included.

## 📋 Evidence design

The bounded replay has `24` complete traces: one new partition-`24` scenario in each of six strata,
each receiving protected-controller, maximum-closing, maximum-separating, and alternating-extrema
command histories. Production exact propagation is compared with fine and coarse independent
`DOP853` references.

Comparisons are explicit and unit-specific. They include state boundaries, collision/depletion times
and ordering, all interval extrema, braking reachability, evaluator duration and dwell metrics, raw
event residuals, and all four frozen classifications. Production and reference traces use separate
evaluator implementations. Fine/coarse self-convergence must remain within `25%` of each applicable
acceptance bound.

Experiment 002b operational and timing-rate evidence is referenced by hash only. Neither campaign is
rerun, and no support claim is added for faster command periods.

## ✅ Decision meaning

A pass means the fixed-command numerical blocker is resolved for the frozen model and replay scope.
It does not qualify flight safety or authorize the full confirmatory campaign. The exact next
scientific blocker is the combined-fault nuisance/information requirement, which requires a separate
prospective design before confirmatory execution.

A failure remains a numerical block and is localized by state quantity, interval extremum, event,
classification, pattern, stratum, and coarse/fine convergence status in the machine-readable result.

The full prospective protocol is frozen in
[`experiments/002c/preregistration.md`](../experiments/002c/preregistration.md).
