# Experiment 002d preregistration

_Bounded combined-fault nuisance and information amendment_

---

> ⚠️ **Evidence boundary:** Experiment 002d estimates only the missing paired nuisance
> quantities for the original F7 synthetic combined-fault stratum. It is not the confirmatory
> campaign, does not test architecture superiority, and does not qualify flight safety.

## 🎯 Frozen question and original stratum map

The original Experiment 002 design enumerates eight equal-weight confirmatory strata. The design
source reviewed before this amendment has SHA-256
`ffd1dba3195edd583797181702125cff4a81456502dba5c2a652ce1aaa75b590`. The mapping is frozen in
`confirmatory-stratum-map.json`:

| Confirmatory stratum | Existing nuisance source |
| --- | --- |
| `F0` nominal | Pilot `P0` |
| `F1` primary range bias | Pilot `P1`, range-bias component |
| `F2` primary dropout | Pilot `P1`, dropout component |
| `F3` monitor-channel fault | Pilot `P2`, frozen 50/50 bias/dropout mixture |
| `F4` shared-cause navigation | Pilot `P3`, frozen 50/50 bias/dropout mixture |
| `F5` persistent model upset | Pilot `P4` |
| `F6` actuator degradation | Pilot `P5` |
| `F7` primary dropout plus actuator degradation | Missing; Experiment 002d |

Thus `F7` is the only wholly unobserved confirmatory stratum. The apparent six-versus-eight count
does not imply a second omitted combined fault: pilot `P1` combined two confirmatory primary-channel
strata as a balanced mixture.

Experiment 002d asks only whether a prospectively sampled F7 nuisance model, combined with the
historical component-level pilot nuisance, supplies enough information to freeze one of the
previously allowed fixed confirmatory sizes (`1,000`, `1,500`, or `2,000` roots per stratum) with at
least 95% marginal power for both H1 and H2.

## 📋 Missing quantities and minimum information

For paired `PD-D` comparisons in F7, record before any design decision:

1. D and PD marginal `analysis_hazard` risks, with controller, invalid-action, numerical, depletion,
   and physical-hazard failures coded adversely as already frozen;
2. directional hazard discordances `PD=1,D=0` and `PD=0,D=1`, total discordance, and its separate
   exact one-sided 95% upper bound;
3. D and PD marginal sustained-success risks;
4. directional sustained-success discordances, total discordance, and its separate exact one-sided
   95% upper bound;
5. adverse-coded failure-cell counts and complete paired-block counts.

The minimum adequate study record is a manifest-complete set of paired D/PD rows that permits all
five quantities and the eight-stratum power calculation. Separate 95% nuisance bounds are used to
match the historical planning convention; no simultaneous-coverage claim is made.

## 🔢 Fixed sample size

The study uses exactly `299` independent F7 root seeds and only the `D` and `PD` arms, yielding
`598` episodes. This is not an effect-detection sample. It is the smallest integer for which zero
incomplete paired blocks gives an exact one-sided 95% upper bound below the frozen `1%`
incompleteness limit:

```text
n=298: 1 - 0.05^(1/298) = 0.0100024
n=299: 1 - 0.05^(1/299) = 0.0099691
```

A pre-outcome least-favorable sensitivity sets both missing F7 discordance rates to `1`, retains the
minimum two-point H1 alternative, and must still identify at least one candidate size with H1 and H2
power above 95%. This shows that 299 roots are requirement/model-validation evidence rather than an
outcome-dependent attempt to discriminate among candidate sizes. The sample will not be enlarged
after outcomes are opened.

## ⚙️ F7 generator and paired execution

The F7 root scenario follows the original design without adding a new fault class:

- primary-dropout onset `U(120,300) s` and duration `U(5,30) s`;
- actuator onset equals dropout onset plus gap `U(-30,30) s`;
- actuator duration `U(30,150) s` and effectiveness `U(0.25,0.75)`;
- the sampling order is dropout onset, dropout duration, onset gap, actuator duration,
  effectiveness;
- all other initial-state, disturbance, channel-noise, latency, quantization, horizon, command-rate,
  and evaluator settings remain the Experiment 002 production settings.

Partition code `25`, F7 stratum code `8`, and named streams are frozen before outcomes. Partition
`16` remains reserved and unmaterialized for the future confirmatory campaign. D and PD share the
same root initial state, disturbances, sensor innovations, latencies, and joint fault realization,
but each arm propagates truth from its own executed commands. Arm order is randomized within each
root. The root seed is the independent unit; commands, evaluator samples, and time steps are never
replicates.

Only D and PD run because H1/H2 nuisance estimation needs no R or PS outcome. No controller,
policy, gate, threshold, recovery corridor, or endpoint is redesigned.

## 🔬 Corrected production and independent evaluation

Experiment 002d imports the corrected production propagator at merged commit `4da0ade`, including
collision-time truncation of extrema and explicit depletion/collision event handling validated by
Experiment 002c. It uses the existing independent truth evaluator, which does not import the
runtime gate. Hidden truth, fault timing, disturbance, and actuator effectiveness remain unavailable
to the policy and gate. The policy artifact and recovery/evaluator inputs remain historical,
hash-verified evidence.

Twenty outcome-blind manifest-selected roots are replayed after execution. Both D and PD episode
rows must reproduce exactly on the same platform. This is a reproducibility check on existing roots,
not new sampling.

## 📈 Frozen eight-stratum power calculation

For each F0-F7 stratum `s`, let `q_Hs` and `q_Ss` be the separate one-sided 95% upper bounds on
paired hazard and success discordance. Every stratum has weight `1/8`.

H1 retains the original requirements alternative:

```text
delta_Hs = -max(0.02, 0.25 * r_D,H,s)
p10 = (q_Hs + delta_Hs) / 2
p01 = (q_Hs - delta_Hs) / 2
```

Two prespecified scenarios are reported: the historical-compatible D-hazard point risk and a
conservative one-sided 95% lower bound on D-hazard risk. In both, `q_Hs` is raised only to
`abs(delta_Hs)` when required for feasibility; `q=1` remains permitted and the old undocumented
`0.99` cap is removed.

H2 uses the original zero risk-difference alternative against the `-0.03` margin, with directional
probabilities `q_Ss/2` and `q_Ss/2`. Each candidate uses `200,000` paired multinomial simulations
from seed `20022508`. The `1.96` convention is preserved because the original plan specified a
two-sided H1 `alpha=0.05` interval and a one-sided H2 97.5% bound. H1 and H2 powers are marginal;
no joint-power claim is made. Monte Carlo uncertainty is reported with Wilson 95% intervals.

A candidate passes only if the lower Monte Carlo interval bound is at least 95% for H1 and H2 in
both planning scenarios. The smallest passing candidate is recommended.

## ✅ Progression decision

The combined-fault information requirement is `resolved_freeze_confirmatory_design` only if all
conditions hold:

- pre-outcome dependency, tests, lint, compilation, source, and publication/privacy checks pass;
- Experiments 002, 002b, and 002c freeze/checksum evidence remains unchanged;
- all frozen 002d hashes verify before execution and after analysis;
- exactly 299 disjoint F7 roots and 598 unique D/PD cells are present;
- incomplete paired blocks are at most 1%, with no outcome-dependent exclusion or replacement;
- same-platform replay passes for both arms on all 20 frozen replay roots;
- only F7 D/PD information outcomes were executed and reserved partition 16 remains unmaterialized;
- at least one allowed candidate meets the frozen H1/H2 marginal-power rule.

If any condition fails, the decision is `blocked`; no confirmatory seeds may be opened. If all pass,
the next action is a separate eight-stratum confirmatory preregistration and freeze at the selected
fixed size. Experiment 002d itself never executes that campaign.

## 🚫 Outcome and interpretation rules

No Experiment 002d effect sign, p-value, interval exclusion, or apparent controller benefit is a
progression criterion. All failures are retained with adverse coding. No seed is replaced. An
unexpected implementation failure stops the write-once workflow rather than triggering selective
reruns. The resulting nuisance estimates apply only to the frozen synthetic F7 generator and do not
estimate real fault prevalence or flight risk.
