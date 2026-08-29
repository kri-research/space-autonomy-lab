# Experiment 002 pilot preregistration

_Frozen hypotheses, analysis, progression, and amendment rules for feasibility evidence_

---

## 🎯 Scope and estimands

The study phase is a six-stratum design-validation pilot with 2,400 paired root-seed blocks and 9,600 controller episodes. It does not test a confirmatory architecture-superiority claim.

For binary endpoint `Y`, the fixed-mixture paired risk difference for arm `A` versus arm `B` is:

```text
RD(A-B) = (1/6) * sum_s mean_i(Y_s,i,A - Y_s,i,B)
```

The principal contrast is `PD-D`. `PS-D` estimates same-information mediation and `PD-PS` estimates the independent-channel increment. `R` is descriptive. Faulted-episode recovery estimands standardize over the five faulted strata with weight `1/5` each.

## 📋 Outcomes and adverse coding

Primary pilot estimates are analysis hazard by 600 seconds and sustained mission success. Physical hazard and collision remain separate observed-truth fields. Controller, invalid-action, and numerical failures are coded as `analysis_hazard=1`, `sustained_success=0`, `recovery_favorable_180=0`, and restricted time unrecovered `=180 s`; they are never relabeled as observed physical events.

Recovery-favorable equals one for `UNAFFECTED` or `RECOVERED` and zero for `GRACEFUL_DEGRADED`, `NOT_RECOVERED`, or `FAILED`. Restricted time unrecovered is zero for `UNAFFECTED`, time from first corridor exit to qualifying re-entry for `RECOVERED`, and otherwise 180 seconds.

The analysis unit is always an episode-level root-seed block. Time samples are never treated as independent observations.

## 🔍 Locked analysis

1. Validate exactly 2,400 unique blocks and four expected arm cells per block.
2. Report arm counts, risks, continuous summaries, and recovery states by stratum and navigation subtype.
3. Report `PD-D`, `PS-D`, and `PD-PS` paired effects by stratum and with fixed standardization.
4. Generate 50,000 percentile bootstrap replicates from seed `200217`, resampling complete four-arm blocks within each stratum.
5. Report two-sided 95% estimation-only intervals, binary discordant-pair counts, and one-sided 95% exact marginal collision upper bounds.
6. Report paired mean differences for continuous expectation estimands; medians and 5th/95th percentiles are descriptive arm summaries.
7. Report complete-block and adverse failure coding. No seed replacement or outcome-dependent exclusion is permitted.
8. Report all planned effects regardless of sign. Pilot intervals and effect directions do not determine architecture favorability.

No pilot p-value, interval exclusion, or observed controller-effect magnitude is a progression criterion. Multiplicity control is deferred to the separately frozen confirmatory protocol; all pilot intervals are labeled estimation-only.

## 📈 Information planning

Confirmatory planning simulations use pilot nuisance estimates only: marginal risks, paired discordance, completion failures, and their conservative uncertainty bounds. The assumed hazard alternative is the greater absolute reduction of two percentage points or 25% of direct-controller risk. The mission alternative is zero risk difference against the minus-three-point noninferiority margin.

Candidate fixed sizes are 1,000, 1,500, and 2,000 root seeds per confirmatory stratum. A size is information-feasible only if estimated power is at least 95% for both H1 and H2. Because the pilot omits the combined-fault stratum, no eight-stratum confirmatory recommendation may pass until its nuisance model is approved prospectively; pilot data must not be used to guess it.

## ✅ Progression criteria

Validity requires all of the following:

- all dependency-lock, tests, lint, protocol, privacy, and source checks pass
- all frozen hashes verify before and after execution
- seed manifest has exactly 400 blocks per stratum and exactly 200/200 mixed components
- every stratum has at least 396 complete four-arm blocks
- policy and gate receive no hidden truth, fault label, disturbance, or latent effectiveness
- matched primary inputs yield identical learned proposals before gating
- equal-spec channel configuration and named-stream independence tests pass
- independent evaluator, continuous collision, reachable stopping, final-window success, and recovery precedence tests pass
- same-platform replay passes for 40 frozen blocks per stratum
- numerical propagation verification passes independently of command-rate sensitivity
- 40 frozen blocks per stratum pass the `1/0.5/0.25 s` command-rate thresholds
- information planning meets the separately approved confirmatory nuisance and power requirements

The decision is `do_not_proceed` after any validity failure, `redesign_required` when validity passes but information requirements do not, and `proceed_to_confirmatory` only when both pass.

## 🔒 Amendment and rerun rules

`experiments/002/deviations.md` is append-only. After freeze, any required change to code, policy, generator, seeds, endpoints, margins, exclusions, analysis, or progression criteria stops the campaign. Partial output is retained, the run is labeled abandoned, a new version and disjoint seed partition are issued, and the full pilot is rerun. A seed is never replaced because of its outcome.

Only an independently identified infrastructure failure from a frozen error-code allowlist may trigger one whole-block retry with the identical seed. Both attempts are retained, and attempt selection follows the frozen rule without consulting controller outcomes.

## ⚠️ Interpretation boundary

The pilot may establish software and design feasibility for its frozen synthetic population. It cannot establish flight safety, real-world fault prevalence, rare-event assurance below its precision, robustness to the omitted combined-fault stratum, policy-training-seed robustness, or confirmatory superiority.
