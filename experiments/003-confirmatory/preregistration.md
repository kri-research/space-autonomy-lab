# Experiment 003 confirmatory preregistration

_Pre-outcome; partition 32 reserved and not materialized_

## Evidence and immutable science

This campaign confirms the frozen Experiment 003 estimator-in-the-loop architecture comparison in
a synthetic engineering stress test. It does not estimate operational fault prevalence, qualify
flight navigation, or establish flight safety. Foundation freeze
`d032ed6b22ff3bb74bc5b03caf2b287a8310b16eb8d76665020a66d98eab2297` is immutable. Its corrected
one-dimensional dynamics, authentic packet timing, two independent navigation filters, estimator
initialization and covariance, NIS/fixed-lag/divergence rules, policy bytes and identity, runtime
gate information boundaries, E0–E6 faults, independent truth evaluator, endpoints, recovery
precedence, and adverse failure coding are reused exactly. No controller, estimator, threshold,
fault, endpoint, or failure rule is redesigned.

The completed pilot passed QC and same-platform reproducibility with 448 complete four-arm blocks
and 1,792 episodes. It did not test H1/H2. Pilot arm-effect direction and patterns did not select
endpoints, thresholds, strata, architecture, or N. The only pilot input to N was paired nuisance
information under the prospectively frozen candidate grid, fixed planning alternatives, 20,000
simulations from seed 300317, and 95% marginal-power lower-bound rule. The smallest passing
candidate was exactly 750 roots per stratum.

## Units, arms, population, and size

The independent and bootstrap unit is one complete `stratum × root_seed` four-arm block. Commands,
packets, states, innovations, NIS, NEES, and evaluator samples are repeated measurements, not
replicates. Each partition-32 root runs `R`, `D`, `PS`, and `PD` once in its deterministic randomized
order. The arm definitions remain those of the foundation.

Each frozen stratum has 750 roots and weight `1/7`: E0 nominal, E1 primary range bias, E2 primary
dropout, E3 primary stale packets, E4 primary covariance underreporting, E5 monitor range bias, and
E6 shared range bias. Thus the schedule is exactly 5,250 paired blocks and 21,000 episodes. Weights
encode stress-test importance, not prevalence.

## Primary gatekeeping

For binary endpoint Y,

```text
RD_Y(A-B) = (1/7) * sum_s mean_i(Y_s,i,A - Y_s,i,B).
```

The primary method is a stratified paired percentile bootstrap of complete four-arm roots within
strata, retaining weight `1/7`, with 50,000 replicates from seed 300318.

1. **H1 safety superiority:** PD-D adverse-coded `analysis_hazard`; reject only when the upper
   endpoint of the two-sided 95% interval is below zero. Favorable classification additionally
   requires the point estimate to be no greater than `-0.02` and at least 25% relative reduction
   when weighted D risk is nonzero; zero D risk cannot satisfy the relative requirement.
2. **H2 mission noninferiority:** test only if H1 passes. PD-D `sustained_success` passes only when
   the one-sided 97.5% lower bound is above margin `-0.03`.

Estimator diagnostics and every secondary or sensitivity result are non-rescuing.

## Secondary family

Exactly four one-sided tests form one Holm family at alpha 0.05:

- H3: `RD_analysis_hazard(PS-D) < 0`;
- H4: `RD_analysis_hazard(PD-PS) < 0`;
- H5a: `RD_recovery_favorable_180(PD-D) > 0` over E1–E6;
- H5b: paired mean restricted unrecovered time `PD-D < 0` over E1–E6.

H3/H4/H5a use discordant-pair exact binomial tests. H5b uses 200,000 paired sign-randomization
draws from seed 300319. Holm adjustment is applied once across all four p-values. R is descriptive.
No subgroup, interaction, threshold, deadline, or extra inferential test may be added.

## Missingness, failures, and sensitivities

Controller, estimator, invalid-action, or numerical failure remains an adverse-valid row with
`analysis_hazard=1`, `sustained_success=0`, recovery `FAILED`, and its specific failure code; it is
not relabeled physical hazard or collision. The retry allowlist is empty. Infrastructure failure
stops with partial output retained and never authorizes replacement.

If incomplete four-arm blocks exceed 1% overall or in any stratum, the campaign is
`inconclusive_invalid`. Exactly three non-rescuing primary sensitivities are permitted:

1. over all scheduled roots, missing PD is adverse and missing D favorable to D;
2. physical-hazard-only PD-D analysis;
3. all roots with D and PD present, even when R or PS is absent.

No other imputation, exclusion, retry, replacement, extension, threshold, transform, or analysis is
allowed.

## Seed, replay, and amendment contract

Partition 32 uses PCG64DXSM and
`SeedSequence([master=3003, partition=32, stratum, replicate, stream])` with the six frozen named
streams. At freeze, `experiments/003-confirmatory/seeds/` and
`results/experiment-003-confirmatory/` must be absent. The foundation-era guard requiring all
Experiment 003 pilot paths to be absent is now phase-inapplicable; the completed pilot must instead
verify exactly.

Only after successful confirmatory freeze/readiness verification may one separate command invoke
the generator. It refuses pre-existing seed or result paths, writes exactly 5,250 roots, verifies
all rows by deterministic rederivation, proves root-ID disjointness from every historical and pilot
manifest, and binds its index to the confirmatory freeze ID. The frozen outcome-blind replay subset
is the first 30 replicate indices in each stratum: 210 roots and 840 episodes, matching the 4%
proportion used in the Experiment 002 final confirmatory campaign.

Any post-freeze change to population, arms, dynamics, observations, estimator, policy, gate, faults,
evaluator, endpoints, recovery, failure coding, margins, multiplicity, N, analysis, or seed
contract abandons this version and requires untouched seeds. Criteria may not be weakened.
