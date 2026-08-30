# Experiment 003 navigation-estimation foundation

_Pre-outcome design and readiness boundary_

> **No Experiment 003 outcomes exist in this foundation.** Pilot and confirmatory seed partitions
> are reserved but not materialized. This is research software for a synthetic engineering stress
> test, not flight-safety or operational-prevalence evidence.

## Scientific purpose

Experiment 002 found a protected-architecture advantage in a one-dimensional stochastic proximity
benchmark, but controllers received synthetic relative-navigation measurements directly.
Experiment 003 asks whether the independently monitored protected architecture retains its
truth-evaluated safety advantage when guidance and runtime assurance act on online state estimates
and covariance under navigation faults.

The primary sequence is:

1. `PD-D` adverse-coded analysis-hazard superiority;
2. if H1 passes, `PD-D` sustained-success noninferiority with margin `-0.03`.

A favorable label also requires at least a 0.02 absolute and 25% relative H1 reduction when D risk
is nonzero. Estimator accuracy is explanatory evidence, not the primary claim.

## Why the plant remains one-dimensional

Planar Hill/Clohessy-Wiltshire dynamics were considered. Introducing them now would also change
control geometry, measurement geometry, learned-policy applicability, fallback behavior, and the
independent safety evaluator. That would confound the estimator question. The selected design
therefore retains the corrected Experiment 002 dynamics, learned policy, controller semantics,
physical evaluator, and mission endpoints while replacing direct measurement use with deterministic
state estimation. Planar orbital coupling remains an explicit next-fidelity limitation.

## Design summary

- **State estimator:** independent primary and monitor float64 linear Kalman filters over range,
  radial velocity, and achieved acceleration.
- **Timing:** explicit measurement/receipt epochs and deterministic one-second fixed-lag replay.
- **Uncertainty:** exact discrete range/velocity covariance for the inherited disturbance generator
  plus frozen achieved-acceleration model uncertainty; Gaussian plus quantization measurement
  covariance; Joseph update; NIS rejection; fail-closed numerical divergence.
- **Arms:** R, D, PS, and PD, all driven by estimated navigation. D versus PD remains primary; PS
  isolates same-channel protection; R is descriptive.
- **Strata:** nominal, primary bias, dropout, stale packets, covariance underreporting, monitor-only
  bias, and shared-cause bias. Equal weights define stress-test importance, not prevalence.
- **Truth boundary:** policy and gate cannot access physical state, realized disturbance, fault
  parameters, offline error, NEES, or evaluator output. NEES and recovery classification are
  evaluator-only.
- **Endpoints:** inherited independent physical hazard and sustained mission success, plus
  adverse-coded estimator/controller/numerical failures.
- **Pilot reservation:** 64 roots per stratum, 448 paired blocks, 1,792 episodes. No roots are
  created by validation or freeze.

## Validation and readiness

Readiness fails closed unless exact/reference dynamics checks, scaled observability, covariance
integrity, delayed-update equivalence, NIS/NEES equation checks, deterministic estimator replay,
forced-divergence fallback, historical evidence verification, tests, lint, compilation,
whitespace, and publication/privacy checks all pass.

The freeze manifest hashes every Experiment 003 design/source/test input, records historical
Experiment 002-family evidence identities, and asserts that `experiments/003/seeds/` and
`results/experiment-003/` are absent. The separate readiness record binds its READY/NOT READY status
to the freeze identifier.

Full hypotheses, analysis, power, recovery, failure, progression, and amendment rules are frozen in
[`experiments/003/preregistration.md`](../experiments/003/preregistration.md).
