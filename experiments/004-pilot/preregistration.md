# Experiment 004 design-validation pilot design freeze

## Status and scope

This artifact defines a **pre-pilot, non-inferential engineering validation** of the frozen
Experiment 004 planar HCW foundation. It does not contain pilot outcomes, a scientific
architecture-benefit hypothesis, a confirmatory estimand, or a confirmatory sample size.
Partition 43 remains unmaterialized until a separate one-time execution task. Partition 44 remains
reserved, unmaterialized, and has no enabled generator.

The question is limited to whether the frozen model, exact event geometry, two navigation channels,
fault routing, vector controller, estimated-geometry monitor, independent evaluator, complete-block
runner, and replay machinery exercise their intended mechanics reproducibly.

## Frozen engineering configurations

Each root is one complete two-configuration block:

1. `primary_reference`: the frozen deterministic vector LQR uses the primary navigation estimate;
   the monitor channel is processed for diagnostics but has no command authority.
2. `independent_monitor_gate`: the same frozen LQR proposal is screened using the independent
   monitor navigation estimate and the frozen vector monitor/fallback primitive.

These labels are diagnostic configurations, not inferential arms. No configuration ranking,
architecture-effect estimate, superiority/noninferiority test, p-value, multiplicity family, or
benefit claim is permitted.

Configuration order is frozen by a case-specific partition-43 stream: the first order is selected
before outcomes for replicate 0 and alternates thereafter. Four roots per case put each
configuration in each order position exactly twice. Initial state, disturbances, measurements,
fault schedule, and actuator realization are paired within a root.

## Frozen matrix and count

The exact eleven cases are in `case-matrix.json`: nominal feasibility; separate forced collision,
keep-out-only, and corridor-departure fixtures; primary bias; primary dropout; monitor bias;
monitor-logic false trip; shared-channel bias; actuation degradation; and additive disturbance.
Physical geometry, mission feasibility, primary-estimator, monitor-estimator, monitor-logic,
shared-cause, actuation, and disturbance records remain separate.

The fixed count is:

- 11 cases × 4 roots = **44 complete blocks**;
- 44 blocks × 2 configurations = **88 episodes**;
- replay subset: replicate 0 in each case = **11 blocks / 22 episodes**.

The count is for design validation, not statistical power. The prospective selection rule evaluates
candidate counts `[2, 4, 6, 8]` using partition-41 mechanics only. A candidate must pass nominal
reachability, deterministic forced-event activation, channel/fault activation, bounded scenario
and nuisance generation, finite/valid covariance, deterministic replay, and runtime checks. It must
also place each configuration in each order position at least twice, which establishes a lower bound
of four. The smallest candidate satisfying every condition is frozen. No configuration difference,
hazard discordance, scientific effect, or hypothesis enters the rule.

## Partition-41 calibration boundary

Partition 41 may be used only before this freeze for event reachability, fixed severity and timing
activation, numerical/event tolerances, bounded initial-state and disturbance envelopes, nuisance
stream checks, and deterministic replay. Calibration records the exact sampled values and checks.
It may not estimate an architecture treatment effect, choose a favorable configuration, select an
outcome direction, optimize hazard discordance, or define a scientific hypothesis. Controller-policy
fit partition 42 is unused; no policy is trained.

## Prospective gates

All gates in `gates.json` are conjunctive and fail closed. They require exact cell completeness,
intended forced-event activation, nominal feasibility, affected/unaffected channel dispositions,
separate technical-domain flags, finite and valid covariance, controller/monitor information
boundaries, no unclassified infrastructure failure, deterministic replay, seed-domain disjointness,
frozen dependency/runtime identity, historical integrity, and a clean publication/privacy scan.
Thresholds, cases, roots, or classifications may not be changed after partition-43 materialization.
There are no outcome exclusions, replacements, extensions, or retries.

## Future execution and analysis

The partition-43 generator is write-once, binds every root to this design freeze ID, refuses any
pre-existing seed/result path, and creates exactly the frozen root count. The future runner writes
only the scheduled complete blocks. Analysis is descriptive, mechanistic, and gate-based: counts,
activation summaries, numerical ranges, and replay identity. No scientific or confirmatory inference
is enabled.

A learned or alternative controller may be considered only in a later, explicit scientific-design
decision. It is not needed to establish engineering validity and is not trained or tuned here.
