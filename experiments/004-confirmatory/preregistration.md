# Experiment 004 confirmatory assurance preregistration

_Pre-outcome design freeze; partition 44 remains reserved and unmaterialized_

## Decision and evidence boundary

The current planar architecture is scientifically sufficient for one bounded question:

> In the equal-weight synthetic challenge population of frozen primary-only navigation bias and
> primary-only packet dropout, does the frozen independent-monitor gate reduce independently
> evaluated physical safety events relative to the same frozen deterministic vector LQR reference,
> without a greater than 5% probability of causing loss of hold acquisition?

This is a deterministic-controller runtime-assurance study. It does not validate a learned or AI
policy: none was trained for Experiment 004. It does not estimate operational fault prevalence,
qualify flight safety, validate 6-DoF dynamics, or provide HIL evidence. The target population is the
frozen 300 s planar HCW synthetic challenge distribution, not spacecraft operations. A null or
inconclusive result is scientifically admissible; the design does not force monitor benefit.

The completed partition-43 pilot was non-inferential. Its configuration-specific event direction,
apparent benefit or harm, hazard discordance, monitor override counts, and individual cases were not
used to select this question, configurations, endpoints, strata, margins, analysis family, or sample
size. Pilot evidence is used only to establish mechanics, nuisance generation, runtime feasibility,
fault activation, covariance validity, and replay capability. No partition-43 effect estimate enters
this design.

## Immutable evidence chain and configurations

The foundation freeze/readiness IDs are
`54a0f1a8dc985fba02973c09ac994fbc76a2ef1abbc7dfe5def82585c85aaa14` and
`fd0ea450e8b5f53a4447cf3910e7e3b494ed6bace33da0055f64e77fd9049404`.
The pilot-design freeze/readiness IDs are
`8f0867a4eaa34c3fb1aef1d8fff62fb579e3099391c5c722b87a3dc6b0746079` and
`5c39bbdc231f7355b9afc79387816b604dbca2f16015e0d179b48f77b6d0d809`.
All foundation and pilot source, thresholds, controller identity, fault severities/timings, geometry,
evaluator, estimator, monitor, and runtime dependencies remain unchanged.

Every root is one paired two-configuration block:

1. `primary_reference`: the frozen bounded deterministic vector LQR uses only the primary
   navigation snapshot. The monitor channel is processed but has no command authority.
2. `independent_monitor_gate`: the identical LQR proposal is screened by the frozen one-step
   estimated-geometry monitor using the independent monitor snapshot. A rejection executes the
   identical frozen LQR evaluated on the monitor snapshot as fallback.

Both are necessary: the first identifies the unmonitored command path; the second changes only the
independent monitor/fallback layer. The comparison makes no AI-specific claim.

## Physical, mission, and mechanism-specific outcomes

The **primary physical safety endpoint** is binary occurrence of any independently evaluated
collision, unauthorized keep-out entry, or corridor departure during the 300 s episode. The exact
truth evaluator consumes physical HCW arcs only, imports neither controller nor estimator, and
returns no information online. The endpoint is not zero by construction: closed-boundary collision,
keep-out, and corridor events remain reachable and are validated prospectively on partition-941
fixtures, while scientific roots use no forced physical fixture.

The distinct **mission-performance endpoint** is gate-induced loss of hold acquisition: the
reference arm acquires the frozen 60 s hold but the monitor-gated arm does not. Hold is never folded
into the physical endpoint.

Mechanisms remain separate in every row and summary:

- primary estimator bias and dropout;
- monitor estimator bias;
- monitor-logic false trip;
- shared-channel navigation bias;
- actuation effectiveness loss;
- exogenous acceleration disturbance;
- invalid action, controller/numerical failure, and infrastructure failure.

Estimator, monitor, shared-cause, actuation, disturbance, or technical flags are never relabeled as
collision, keep-out entry, or corridor departure. Invalid action, nonfinite/numerical failure,
missing cells, or infrastructure failure invalidates confirmatory inference rather than being
imputed as a physical event. There is no retry, replacement, extension, or outcome-dependent
exclusion.

## Frozen strata and population

The scientific population excludes pilot forced-collision, forced-keep-out, and forced-corridor
fixtures. Eight stochastic strata reuse the frozen planar generator and severities:

- 64 nominal roots (`P00`), descriptive concurrent control;
- 534 primary-only navigation-bias roots (`P04`), primary weight 0.5;
- 534 primary-only dropout roots (`P05`), primary weight 0.5;
- 64 monitor-only navigation-bias roots (`P06`), descriptive negative control;
- 64 monitor-logic false-trip roots (`P07`), descriptive negative control;
- 64 shared-navigation-bias roots (`P08`), shared-cause claim boundary;
- 64 actuation-degradation roots (`P09`), post-command claim boundary;
- 64 disturbance-burst roots (`P10`), exogenous-plant claim boundary.

The primary estimand weights P04 and P05 equally by design; these weights represent scientific
challenge importance, not prevalence. Other strata are prospectively descriptive and cannot rescue
the primary result. There is no secondary inferential family, subgroup test, interaction, or
outcome-driven stratum pooling.

## Pairing, order, and unit of inference

The independent unit is one complete `stratum × root_seed` paired block. Commands, packets,
substeps, evaluator samples, and event timestamps are repeated measurements, not replicates. Within
a root, initial state, process disturbance, primary and monitor measurement draws, fault schedule,
actuator realization, and controller identity are identical across configurations.

Partition 44 uses PCG64DXSM and

```text
SeedSequence([4004, 44, geometry_case, fault_case, replicate, stream])
```

with the eight frozen named streams. The first within-block configuration order is selected by the
frozen order stream at replicate zero and alternates thereafter. Every frozen stratum count is even,
so each configuration appears first exactly half the time. No planning/calibration seed domain is
needed; sample size is analytic. Partition 44 is disjoint from 41, 42, 43, 941 and all historical
root namespaces.

## Primary estimand and fixed gatekeeping

For each primary root let `Y_R` and `Y_G` be the binary physical endpoint for reference and gate.
The primary estimand is

```text
Delta_safety = 0.5 E_P04[Y_G - Y_R] + 0.5 E_P05[Y_G - Y_R].
```

Beneficial discordance is `Y_R=1, Y_G=0`; harmful discordance is `Y_R=0, Y_G=1`.

**H1 physical superiority** tests `H0: Delta_safety >= 0` against `H1: Delta_safety < 0` using the
exact one-sided paired-discordance (McNemar/sign) test at alpha 0.025. H1 passes only if the exact
p-value is at most 0.025 **and** the observed gate-minus-reference risk difference is at most -0.05.
The practical floor was selected prospectively and not from partition 43.

Only if H1 passes, **H2 mission protection** tests the probability of gate-induced hold loss against
a 0.05 margin using an exact one-sided binomial test at alpha 0.025. H2 is
`H0: p_harm >= 0.05` versus `H1: p_harm < 0.05`. A favorable classification requires valid fixed
cells, H1, and H2. Fixed-sequence gatekeeping controls the one-sided familywise alpha without a
second multiplicity adjustment. All mechanism-specific summaries outside H1/H2 are descriptive and
non-rescuing.

## Prospective sample size and fixed count

No observed partition-43 treatment effect is used. The primary calculation assumes the
variance-worst paired binary case in which every root is discordant. Under H0, beneficial
probability among discordances is 0.5. A prospective 10 percentage-point net beneficial
discordance planning alternative gives probability 0.55. The smallest **even** N whose exact
one-sided test has at least 90% power at alpha 0.025 is 1,068 primary roots (critical beneficial
count 567 if all are discordant; achieved power approximately 0.90059; achieved alpha approximately
0.02333). Equal allocation gives 534 roots in each primary stratum. This is a planning alternative,
not an effect estimate or guaranteed result.

The mission margin is 0.05 with planning harm rate 0.01; at N=1,068 its exact test is not
sample-size limiting. Sixty-four roots in each nonprimary stratum provide balanced deterministic
order and bounded mechanistic evidence without creating extra inferential claims.

The immutable total is therefore **1,452 paired blocks × 2 configurations = 2,904 episodes**.
There is no adaptive extension, conditional power, interim analysis, or sample-size re-estimation.

## Replay, execution, and write-once contract

The outcome-blind replay subset is replicates 0-7 in every stratum: **64 blocks / 128 episodes**.
Replay selection is fixed before partition-44 materialization and requires canonical row and trace
identity on the frozen runtime/platform.

The partition-44 generator exists only as code at freeze. It may run only after exact confirmatory
freeze and readiness self-hashes verify. It refuses any pre-existing seed or result path, binds every
row and the seed index to the exact freeze/readiness IDs and seed-contract hash, writes exactly 1,452
roots, rejects root overlap or deterministic count drift, and cannot replace or extend a schedule.
This design task does not invoke it.

Any change to the question, population, arm semantics, fault envelope, endpoint, evaluator,
analysis, alpha, margins, N, replay subset, or failure policy abandons this freeze and requires a new
untouched seed domain. No outcome-driven threshold, exclusion, sensitivity, stratum, rerun, or
hypothesis switch is permitted.
