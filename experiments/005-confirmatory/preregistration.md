# Experiment 005 partition-53 confirmatory preregistration

_Pre-outcome design freeze; partition 53 remains reserved, unmaterialized, and unexecuted._

## Confirmatory question and evidence boundary

The smallest defensible confirmatory question is a direct nonlinear-truth transfer of the
pre-outcome Experiment 004 assurance question:

> In the equal-weight synthetic challenge population of frozen primary-only navigation bias and
> primary-only packet dropout, does the frozen independent-monitor gate reduce independently
> evaluated physical adverse events relative to the same frozen deterministic vector LQR
> reference, without a 5% or greater probability of causing loss of hold acquisition?

The physical plant is the frozen nonlinear central-gravity chief/deputy truth system. Both online
navigation filters, the controller, and the monitor retain the frozen planar HCW model and receive
no nonlinear truth or physical-event evidence online. The target population is the frozen 300 s
synthetic challenge distribution, not operational spacecraft encounters.

The question, paired configurations, composite physical endpoint, mission endpoint, alpha,
practical effect floor, harm margin, and planning alternative all existed in the pre-outcome
Experiment 004 confirmatory design. They are transferred without using a partition-54 architecture
effect, event rate, event direction, discordance count, or configuration ranking. Partition 54 is
used only to establish nonlinear-runner mechanics, intended fault activation, finite numerical and
covariance behavior, exact replay, process launch, checkpoint continuation, and frozen-source
integrity. A null, harmful, or inconclusive result is admissible.

## Immutable lineage

The design is conditional on the complete Experiment 005 chain:

1. nonlinear two-body truth foundation, freeze
   `921c481726d6f078621ff3a355a7803af803bdc61a8a2da07ffb974a433b3be8` and readiness
   `9ec734543fd3580e9a2990a16dc56747a0f75334f76bd2c7ae1fdc3647732e67`;
2. partition-52 transfer-pilot design, freeze
   `3fa9fd6e9e4d3146af6495c07599ed792cfb52ce16e90d0dca234ed64295be8b` and readiness
   `ebc98c9eb9b14d2dc85351d68ca3c5c84791e050f2be038c7fdd9067ef6ce2f3`;
3. the preserved, permanently invalid partition-52 infrastructure attempt;
4. the outcome-blind partition-54 replacement amendment, freeze
   `01504ff16ccf8a79dad67f88c4d40920be39dfa929169ccb72fdfcede18b34c1` and readiness
   `3181e1a9b40c3ab32b684934d8c975b3eeeee44c2b38cd9dc80e0f0c589328c0`;
5. the sole valid partition-54 noninferential execution and closeout; and
6. restoration of `.github/workflows/ci.yml` to its foundation SHA-256
   `bc033a3ddc0114964059760a6372b8da233b8aac1026d24af2a795c5b607f420`.

The earlier NOT READY audit is retained unchanged. Any later mismatch in these identities closes
readiness before partition-53 materialization.

## Cases, configurations, and independent unit

Only two stochastic cases enter the scientific population:

- `T03_primary_navigation_bias`: frozen +8 m primary-only radial bias for 30 s;
- `T04_primary_navigation_dropout`: frozen 6 s primary-only packet dropout.

They receive fixed design weights 0.5 and 0.5. These are scientific challenge weights, not
operational prevalence estimates. The partition-52/54 forced truth-event fixture, isolated
model-mismatch fixture, nominal case, monitor-side faults, shared-cause faults, actuation loss, and
disturbance burst are not added as inferential or rescuing strata. Their mechanics were already
covered by the noninferential pilot.

Every root is one paired two-configuration block:

1. `primary_reference`: the frozen deterministic vector LQR uses the primary HCW navigation
   snapshot; the monitor channel has no command authority.
2. `independent_monitor_gate`: the identical proposal is screened by the frozen estimated-geometry
   gate using the independent monitor HCW snapshot; rejection uses the frozen monitor-snapshot
   fallback.

Initial truth state, process perturbations, both navigation-noise streams, fault schedule, actuator
realization, and controller identity are common within a root. The independent unit is the complete
paired root block. Commands, packets, integration substeps, event samples, and timestamps are
repeated measurements, not replicates.

## Endpoints and estimands

For primary-case root `i`, let `Y_Ri` and `Y_Gi` indicate any independently evaluated physical
collision, unauthorized keep-out entry, or corridor departure in the reference and gated episodes.
The primary estimand is

```text
Delta_safety = 0.5 E_T03[Y_G - Y_R] + 0.5 E_T04[Y_G - Y_R].
```

The primary endpoint definition is not altered in response to partition-54 observations. If the
composite is non-discordant or saturated in partition 53, H1 fails and the study is inconclusive;
no component is removed or substituted.

The gatekept mission estimand is

```text
p_harm = P(reference acquires the frozen 60 s hold and monitor-gated does not)
```

in the same equal-weight primary population. Component physical events, arm-specific hold
acquisition, minimum separation, maximum admissible-position excess, monitor overrides, estimator
dispositions, covariance diagnostics, and nonlinear-minus-HCW residuals are secondary descriptive
endpoints only. There is no secondary inferential family, subgroup test, interaction test, or
architecture ranking.

## Hypotheses, gatekeeping, and multiplicity

Beneficial discordance is `Y_R=1, Y_G=0`; harmful discordance is `Y_R=0, Y_G=1`.

**H1 physical superiority** tests `H0: Delta_safety >= 0` against `H1: Delta_safety < 0` with the
exact one-sided paired-discordance test at alpha 0.025. H1 passes only if the exact p-value is at
most 0.025 and the observed gate-minus-reference risk difference is at most -0.05.

Only if H1 passes, **H2 mission protection** tests `H0: p_harm >= 0.05` against
`H1: p_harm < 0.05` with an exact one-sided binomial test at alpha 0.025. Fixed-sequence gatekeeping
controls the one-sided familywise alpha at 0.025 without a further multiplicity adjustment. H2 is
not tested when H1 fails. Descriptive endpoints cannot rescue either gate.

## Prospective sample size and precision basis

No partition-54 outcome enters the calculation. The primary calculation uses the same prospective
smallest effect and exact worst-case paired-binary construction as the pre-outcome Experiment 004
design. With every root discordant, the null beneficial-discordance probability is 0.5. A
10 percentage-point net reduction corresponds to beneficial probability 0.55 and maximizes the
paired-difference variance among distributions having that net reduction.

The smallest even N with at least 90% exact one-sided power at alpha 0.025 is 1,068 paired roots.
If all roots are discordant, the critical beneficial count is 567, achieved alpha is approximately
0.0233271, and achieved power is approximately 0.900587. N=1,066 is insufficient. Equal allocation
therefore gives 534 roots in each primary case.

For H2, at N=1,068 the exact rejection region is at most 39 gate-induced hold losses. It has size
approximately 0.021700 at the 0.05 margin and power greater than 0.9999999999 at the prospective
0.01 planning rate, so H2 is not sample-size limiting. The immutable total is **1,068 paired blocks
and 2,136 episodes**. There is no interim analysis, conditional power, adaptive extension, or
sample-size re-estimation.

## Analysis and interpretation

The fixed schedule must first pass exact completeness, uniqueness, finite nonlinear truth,
information-boundary, fault-activation, infrastructure, and replay checks. Every episode must have
minimum estimator-covariance eigenvalue at least `-1e-12`, maximum covariance trace strictly below
`1,000,000`, exactly 30 active primary-fault packets in `T03` or 6 in `T04`, and zero active monitor
fault packets. These are the frozen transfer-pilot validity gates, not outcome-derived thresholds.
Only then are the two paired exact tests evaluated. The pooled test equals the fixed equal-weight
estimand because both cases have exactly 534 roots.

A **favorable** classification requires every validity gate, H1 including its 5 percentage-point
practical floor, and gatekept H2. A valid H1 failure is **inconclusive**, not evidence of equality or
safety. H1 success followed by H2 failure is **inconclusive with mission-harm gate failure**. A
harmful observed direction is reported as such without switching hypotheses. Any invalid fixed-cell
or integrity gate gives **invalid/inconclusive** with no confirmatory inference.

The claim is limited to the frozen deterministic controller and monitor in the two-case synthetic
nonlinear central-gravity testbed. It does not estimate operational fault prevalence, qualify flight
safety, validate six-degree-of-freedom dynamics, supply hardware-in-the-loop evidence, or support a
learned-policy claim.

## Missingness, failure, checkpoint, and replacement policy

Missing, duplicate, extra, corrupt, foreign, or noncanonical cells are never imputed or excluded.
Any numerical invalidity, nonfinite state, infrastructure failure, terminal worker record, seed
mismatch, or incomplete fixed schedule closes inference. A failed block is not retried and no root
is replaced.

A process interruption that publishes no terminal worker failure may continue the same frozen
campaign. Continuation first verifies every existing campaign-bound content-hashed shard and then
executes only missing unpublished complete paired blocks. Completed valid blocks are never
recomputed. Corrupt or conflicting evidence fails closed. Final assembly follows frozen case,
replicate, and within-block order, independent of worker completion order.

Partition 53 is single-use. If it becomes invalid, it is permanently retired. Any scientifically
justified replacement requires a separate prospective amendment and a fresh untouched partition;
no replacement, extension, threshold change, endpoint switch, or root substitution is authorized
by this freeze.

## Seed, replay, materialization, and execution contract

Partition 53 uses PCG64DXSM and

```text
SeedSequence([5005, 53, geometry_case, challenge_case, replicate, stream])
```

with the frozen Experiment 005 streams 201-207. Root identities are
`experiment005:53:<case_code>:<replicate>`. They must be disjoint from partitions 51, 52, 54, and
951 and every historical root namespace. Within each case, the partition-specific order stream
selects the first configuration for replicate 0 and order alternates thereafter; 534 is even, so
each configuration appears first 267 times per case.

The deterministic replay subset is replicates 0-7 in both cases: **16 paired blocks and 32
episodes**. Replay requires byte-identical canonical episode rows and trace digests on the frozen
runtime/platform.

The generator exists only as authorized source code at this freeze. It may run only after the
confirmatory freeze ID, readiness ID, lineage, source hashes, and seed-contract hash all verify. It
refuses any pre-existing partition-53 seed or result path, stages a canonical fixed schedule, and
publishes the directory once. This design task does not invoke the generator and creates no
partition-53 seed, checkpoint, episode, replay, analysis, or result file.

## READY / NOT READY rule

`READY_FOR_PARTITION_53_EXECUTION` requires all of the following conjunctively:

- exact branch/base ancestry and every frozen Experiment 005 identity;
- preserved invalid partition-52 audit and valid partition-54 closeout/checksums/replay;
- restored foundation workflow SHA-256;
- exact inherited cases, challenge values, endpoints, thresholds, configurations, and sample size;
- analytic power and mission-margin calculations reproduced;
- generator present but never invoked, with seed and result targets absent;
- zero partition-53 root rows in repository evidence;
- deterministic import-safe process-pool and fail-closed checkpoint protocol;
- phase-appropriate tests, Ruff, compilation, stable gate, diff hygiene, and public-content scan.

Any failed item yields `NOT_READY`; there is no waiver. The only authorized next scientific action
after independent review and merge is one write-once partition-53 materialization and checkpointed
execution under this freeze. No additional experiment is authorized.
