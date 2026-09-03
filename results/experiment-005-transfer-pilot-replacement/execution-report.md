# Experiment 005 partition-54 transfer-pilot closeout

## Decision

**All prospectively frozen design-validation gates passed.** Partition 54 contains 20 complete
paired blocks and 40 episodes. The 10-block, 20-episode replay is byte-identical to the frozen
replicate-0 subset. No infrastructure failure, retry, replacement root, extension, or partition-52
reuse was observed. Partition 53 remains untouched.

This is a noninferential mechanics result. No architecture effect, superiority, noninferiority,
hazard rate, confidence interval for an architecture effect, ranking, or operational event rate was
estimated.

## Frozen gate results

- Seed and cell identity: 20/20 unique partition-54 roots and 40/40 canonical episode rows; no
  historical root overlap and no partition-52 scenario-hash reuse.
- Checkpoints: 20/20 campaign shards and 10/10 replay shards passed campaign, content-hash,
  canonical-order, and assembled-output checks.
- Nonlinear truth and covariance: every episode was finite and valid; minimum covariance eigenvalue
  was `1.21121e-06` and maximum covariance trace was
  `123.701` against frozen limits `-1e-12` and `<1e6`.
- Truth-event fixture: keep-out entry occurred in 4/4 episodes and collision in 0/4.
- Model-mismatch fixture: every episode had 120 finite observations and a positive residual;
  maximum position and velocity residuals were `5.86761e-09 m`
  and `2.86179e-09 m/s`. No favorable or unfavorable absolute
  mismatch threshold was defined.
- Primary, monitor, monitor-logic, shared-navigation, actuation, and disturbance activation gates
  all passed with unaffected channels remaining inactive.
- Frozen source, design, information-boundary, runtime, replay, and historical partition-52 evidence
  checks passed.

## Descriptive observations

Across all 40 episodes there were
0 collisions,
8 keep-out entries,
40 corridor departures, and
24 hold acquisitions. The nominal case
acquired hold in 4/4 episodes with no collision or keep-out entry. The actuation-degradation case
entered keep-out in 4/4 episodes with no collision and no hold. Every episode recorded corridor
departure. These are descriptive observations, not architecture comparisons or additional
progression criteria.

## Progression

The frozen progression decision is `pilot_design_gates_passed`. A separate prospective
partition-53 confirmatory-design freeze is scientifically justified solely because every frozen
conjunctive design-validation gate passed. This closeout does not authorize a confirmatory campaign
and does not create, materialize, or execute partition 53.

The smallest next task is to freeze a separate prospective partition-53 confirmatory design that defines its scientific question, estimands, case matrix, sample size and power basis, gatekeeping and multiplicity, analysis, replay subset, seed contract, and write-once execution protocol while leaving partition 53 unmaterialized and unexecuted.
