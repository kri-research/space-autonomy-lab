# Experiment 002 confirmatory campaign

_Final eight-stratum design and pre-outcome freeze_

---

> **Evidence boundary:** This is a confirmatory comparison within the frozen one-dimensional
> synthetic generator. It is not flight-safety evidence and does not estimate operational fault
> prevalence.

## Final design

The campaign has eight equal-weight strata, 1,000 independent root seeds per stratum, and four
paired arms (`R`, `D`, `PS`, `PD`):

```text
8 strata × 1,000 roots × 4 arms = 32,000 episodes
```

The stratum map is F0 nominal, F1 primary range bias, F2 primary dropout, F3 monitor-channel
fault, F4 shared-cause navigation, F5 persistent model upset, F6 actuator degradation, and F7
primary dropout plus actuator degradation. F3 and F4 each retain an exact outcome-blind 500/500
range-bias/dropout mixture. Every stratum has weight `1/8`; observed frequencies cannot reweight
the estimand.

The design size is the smallest candidate resolved by Experiment 002d. The completed 002d
analysis selected 1,000 roots per stratum after both H1 and H2 exceeded the frozen 95% marginal
power requirement under historical-compatible and conservative nuisance scenarios.

## Frozen implementation lineage

The campaign uses the frozen policy artifact without retraining, refitting, replacement, or
controller redesign. It uses the 600 s horizon, 1 s command/observation period, 0.25 s exogenous
path, independent truth evaluator, recovery corridor, and corrected production dynamics validated
by Experiment 002c. The invalid multi-rate invariance criterion from the original pilot is not a
confirmatory gate; faster command periods are outside this campaign.

H1 uses adverse-coded `analysis_hazard`, so propellant depletion and controller, invalid-action, or
numerical failures cannot make a controller appear safer. Physical hazard and collision remain
separate reported outcomes. H2 uses sustained mission success. The full estimand, gatekeeping,
secondary, missingness, and sensitivity rules are in
[`experiments/002-confirmatory/preregistration.md`](../experiments/002-confirmatory/preregistration.md).

## Reserved partition rule

Partition 16 is still only a reservation at freeze. No confirmatory scenario row or outcome is
created by validation, freeze, or freeze verification. After the freeze verifies, a separate
write-once command may materialize exactly 8,000 deterministic scenario rows from the frozen
partition/stratum/replicate/stream derivation. That command re-verifies the freeze internally,
refuses pre-existing seed or result files, binds the generated index to the freeze identifier, and
checks exact counts, mixtures, scenario hashes, and historical disjointness before any campaign run
is permitted.

Any freeze drift, reservation mismatch, pre-existing output, wrong count, or inability to derive
the declared eight-stratum manifest blocks execution. Seeds are never replaced or added because of
outcomes.
