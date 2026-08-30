# Experiment 003 confirmatory design

_Pre-outcome seven-stratum freeze; partition 32 remains unmaterialized_

> This is a confirmatory engineering stress test in the frozen one-dimensional synthetic
> Experiment 003 generator. Equal stratum weights do not estimate operational prevalence, and no
> result establishes flight safety.

## Frozen campaign

The independent unit is one complete `stratum × root_seed` block. Every root runs the unchanged
`R`, `D`, `PS`, and `PD` arms once in deterministic randomized order:

```text
7 equal-weight strata × 750 partition-32 roots × 4 arms = 21,000 episodes
```

The seven E0–E6 strata, dynamics, packets, estimators, learned-policy identity, runtime-assurance
information boundaries, faults, independent evaluator, endpoints, recovery rules, and adverse
failure coding are inherited without change from foundation freeze
`d032ed6b22ff3bb74bc5b03caf2b287a8310b16eb8d76665020a66d98eab2297`.

The size is the smallest predeclared candidate passing both frozen marginal-power lower-bound
rules in the completed 448-block/1,792-episode design-validation pilot. Pilot arm-effect direction
or patterns did not choose endpoints, thresholds, strata, architecture, or sample size; N used only
the prospectively frozen nuisance-resolution rule with fixed planning alternatives.

## Locked inference

H1 is PD-D `analysis_hazard` superiority: the upper endpoint of the two-sided 95% stratified paired
percentile-bootstrap interval must be below zero. A favorable classification also requires a point
estimate no greater than `-0.02` and at least 25% relative reduction when D risk is nonzero. Only if
H1 passes, H2 tests PD-D `sustained_success` noninferiority: the one-sided 97.5% lower bound must be
above `-0.03`. The bootstrap uses 50,000 replicates, seed 300318, complete root blocks, and fixed
weight `1/7` per stratum.

H3, H4, H5a, and H5b are one Holm family at alpha 0.05. H5b uses 200,000 paired sign-randomization
draws from seed 300319. Exactly three primary sensitivities are allowed: worst-case missing primary
cells, physical-hazard-only PD-D, and all available D/PD pairs. No additional analysis is allowed.

## Write-once boundary

Freeze and readiness require the frozen foundation source hashes, pilot result/QC/reproducibility,
historical Experiment 002 evidence, numerical/observability/covariance and interface checks,
dependency/runtime identity, and publication/privacy checks to pass. The old foundation assertion
that all Experiment 003 seeds/results are absent is phase-inapplicable after the pilot; current
verification instead requires the frozen pilot to verify and the confirmatory seed/result paths to
remain absent.

Runtime dependency versions are frozen and validity-gated. Host operating system and machine architecture are recorded as provenance but are not required to match the original macOS/arm64 design host, so independent CI/reverification can run on a supported host with the same frozen Python/NumPy/SciPy environment.

Only a later explicit materialization task may reverify this freeze and derive partition 32. It must
write exactly 5,250 roots, prove disjointness from all historical and pilot roots, select the first
30 replicate indices per stratum for the frozen 210-root/840-episode replay, bind its index to this
confirmatory freeze identifier, and refuse existing outputs, replacement, extension, or count
drift.
