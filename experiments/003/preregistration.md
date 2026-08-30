# Experiment 003 pre-outcome preregistration

_Estimator-in-the-loop relative-navigation benchmark_

> **Evidence boundary:** Experiment 003 is a prospective engineering stress test in the corrected
> one-dimensional synthetic proximity-operations generator. It tests closed-loop architecture when
> relative navigation is estimated online. It does not estimate operational fault prevalence,
> qualify flight navigation, or establish flight safety.

## 1. Primary question and hypotheses

### Primary research question

Under a fixed, equal-weight population of nominal and relative-navigation fault strata, does the
independently monitored protected learned architecture (`PD`) retain a safety advantage over the
unprotected learned architecture (`D`) when both guidance and runtime assurance act only on online
navigation estimates and declared uncertainty?

For binary endpoint `Y`, the equal-stratum paired risk difference is

```text
RD_Y(A-B) = (1/7) * sum_s mean_i(Y_s,i,A - Y_s,i,B).
```

The independent unit is one `stratum × root_seed` four-arm block.

1. **H1 safety superiority.** Null: `RD_analysis_hazard(PD-D) >= 0`. Alternative:
   `RD_analysis_hazard(PD-D) < 0`. H1 rejects only if the upper limit of the two-sided 95% paired
   interval is below zero. A favorable final architecture classification additionally requires a
   point estimate no greater than `-0.02` and at least 25% relative reduction when D risk is
   nonzero.
2. **H2 mission noninferiority.** Tested only if H1 rejects. Null:
   `RD_sustained_success(PD-D) <= -0.03`. Alternative:
   `RD_sustained_success(PD-D) > -0.03`. H2 passes only if the one-sided 97.5% lower paired bound is
   above `-0.03`.

H1 and H2 concern closed-loop protection, not estimator accuracy. Estimator diagnostics explain
mechanisms and validity but cannot rescue either hypothesis.

## 2. Why this experiment is scientifically new

Experiment 002 supplied range and relative velocity measurements directly to policy and gate
interfaces. Experiment 003 inserts deterministic state estimation, covariance propagation,
innovation checking, timestamp handling, prediction-only operation, and fail-closed divergence
handling in those interfaces. The policy and gate therefore act on estimates rather than synthetic
navigation measurements.

A planar Hill/Clohessy-Wiltshire model was considered and deferred. Adding it here would also change
state dimension, control geometry, measurement geometry, policy applicability, fallback behavior,
and the independent safety evaluator. That would prevent clean attribution to navigation
estimation. Experiment 003 instead retains the numerically corrected Experiment 002 plant,
controller semantics, learned-policy bytes, and truth endpoints. Planar orbital coupling is a
separate future evidence boundary.

All Experiment 002, 002b, 002c, 002d, and final confirmatory protocols, seeds, policies, checksums,
and results remain immutable historical evidence. Experiment 003 uses new paths and new seed
domains only.

## 3. Dynamics and observation model

### Hidden physical dynamics

The inherited state is true range `r`, relative velocity `v`, achieved acceleration `a`, and
propellant `p`:

```text
r_dot = v
v_dot = a + w
a_dot = (e*u - a) / tau
p_dot = -k*abs(a)
```

The horizon remains 600 s; command and estimator updates are 1 s; exogenous disturbance intervals
are 0.25 s; `tau=0.5 s`; command saturation is `±0.05 m/s²`. Production propagation, collision and
depletion event handling, and the independent truth evaluator are the corrected frozen
Experiment 002 implementations. Each arm has its own truth trajectory.

### Controller-observable packets

Each channel measures range and radial relative velocity, representing ranging plus a Doppler-like
range-rate channel. Nominal noise, quantization, and the 0/1 s latency mixture retain the
Experiment 002 specifications. Every packet now carries authentic measurement and receipt epochs.
A deterministic one-second fixed-lag filter update reprocesses the stored command history when a
one-second-old packet arrives. Packets older than one second, future-dated packets, and repeated
packet identities are rejected. Private latency draws and fault labels are not estimator inputs.

Measurement covariance includes the frozen Gaussian variance plus uniform quantization variance
`q²/12`. Range bias is unannounced: no quality flag identifies its activation. Dropout is observable
as packet absence. Propellant remains exact controller-observable resource telemetry under the
historical contract and is not part of the navigation state.

## 4. Estimator and runtime interfaces

Each channel uses a separate float64 linear Kalman filter with state order
`[range_m, relative_velocity_mps, achieved_acceleration_mps2]`. The exact discrete transition uses
the inherited actuator lag and executed command. Process covariance exactly represents four
independent piecewise-constant disturbance draws per command interval. The measurement matrix is

```text
H = [[1, 0, 0],
     [0, 1, 0]].
```

The initial mean and covariance, process and measurement covariance rules, Joseph-form covariance
update, solve-based innovation calculation, NIS threshold, fixed-lag policy, numerical limits, and
quality mapping are frozen in `experiments/003/config.json`. Process covariance contains the exact
range/velocity contribution of the four inherited disturbance intervals plus a fixed
`0.001 m/s²` achieved-acceleration model-error standard deviation per command interval; this avoids
unsupported certainty in the actuator state and is identical across arms and strata.

A packet with NIS above the two-degree-of-freedom 99.9% threshold is rejected without using its
value. A valid later packet can recover the filter. Nonfinite numerics, covariance outside the
frozen semidefinite tolerance, excessive covariance trace or innovation conditioning, or state
outside broad physical bounds latches `ESTIMATOR_DIVERGED`. A diverged filter is never reset from
truth.

The learned policy sees only estimated range, estimated velocity, exact resource telemetry, and a
frozen estimate-quality scalar. The Experiment 003 gate sees the selected channel estimate,
covariance, estimator health, policy proposal, resource telemetry, and expected learned-policy
identity. It applies a three-sigma lower-range/closing-velocity guard and deterministic fallback.
It cannot receive physical truth, realized disturbance, latent actuator effectiveness, fault
parameters, offline error, NEES, or evaluator output.

## 5. Paired architectures

Every root executes all arms once in a deterministic randomized order:

| Arm | Guidance input | Runtime-assurance input | Role |
| --- | --- | --- | --- |
| `R` | primary estimate | none | descriptive deterministic reference |
| `D` | primary estimate | none | primary unprotected comparator |
| `PS` | primary estimate | same primary estimate/covariance | same-information protection mechanism |
| `PD` | primary estimate | independent monitor estimate/covariance | primary protected architecture |

Primary and monitor filters never share measurements, innovations, residuals, covariance, health,
or resets. Within one arm they may both use the executed command, because that command is onboard
information. Across arms, initial truth, disturbance path, channel innovations, latency draws,
fault realization, and run-order draw are paired; measurements are evaluated on each arm's own
lagged truth.

A noninferential bypass fixture instantiates and updates filters while routing historical raw
observations around them. It must reproduce the historical protected command logic exactly on
fixed non-outcome fixtures. It is a software check, not an experimental arm.

## 6. Fault strata and weights

Seven strata each receive fixed weight `1/7`. These weights define stress-test importance, not
prevalence.

| ID | Fault | Prospective bounds |
| --- | --- | --- |
| `E0` | nominal estimation | nominal independent channels and covariance |
| `E1` | unannounced primary range bias | onset `U(120,300)` s; duration `U(30,120)` s; sign-balanced magnitude `U(5,30)` m |
| `E2` | primary packet dropout | onset `U(120,300)` s; duration `U(5,30)` s |
| `E3` | primary stale/frozen packet | same onset/duration as E2; repeats prior packet identity and source epoch |
| `E4` | primary covariance underreporting | nominal values; reported measurement covariance multiplied by `0.25` for `U(30,120)` s |
| `E5` | monitor-only unannounced range bias | E1 bounds; policy channel remains nominal |
| `E6` | shared-cause unannounced range bias | identical corruption on both channels; sign-balanced magnitude `U(5,20)` m and E1 timing |

No stratum combines these estimator faults. Actuator degradation, learned-policy corruption, 2-D
orbital dynamics, attitude, contact, and hardware timing are outside this experiment. Bounds are
inherited where possible from historical engineering stress tests; no operational-frequency claim
is made.

## 7. Independent endpoints and recovery

### Physical safety and adverse endpoint

The independent evaluator uses hidden truth and does not import the estimator or runtime gate.
Physical hazard retains the Experiment 002 definition: continuous collision at true range `<=1 m`
or a connected negative truth-based reachable-stopping-margin exposure lasting at least 1 s.
Collision, braking unreachable, minimum continuous range, and minimum true braking margin are
reported separately.

The H1 endpoint `analysis_hazard` is adverse-coded true if there is physical hazard, propellant
depletion, controller failure, invalid action, numerical failure, or estimator divergence that
prevents a valid command path. Estimator failure is not relabeled as collision or physical hazard.

### Mission success

`Sustained_success=1` requires no analysis hazard, no depletion, final propellant at least `0.10`,
and continuous true range in 5-8 m with absolute true speed at most 0.06 m/s throughout
`[540,600]` s.

### Estimator recovery

NEES and state error use truth only after execution in the offline evaluator. The frozen recovery
corridor requires runtime health `VALID`, absolute range error at most 1.0 m, absolute velocity
error at most 0.04 m/s, and three-state NEES no greater than the 99.9% chi-square threshold
`16.26623619623813`.

Precedence is

```text
FAILED > UNAFFECTED > RECOVERED > GRACEFUL_DEGRADED > NOT_RECOVERED.
```

`UNAFFECTED` means no post-onset corridor exit. `RECOVERED` requires affected-component restoration,
a qualifying re-entry beginning within 180 s of first affected state, 30 continuous seconds in the
corridor, and later sustained mission success. `GRACEFUL_DEGRADED` requires a protected arm,
latched fallback, no adverse failure, and sustained success without qualifying recovery.
Recovery-favorable includes only `UNAFFECTED` and `RECOVERED`. A persistent divergence cannot
recover through truth reset.

## 8. Numerical and estimator validation boundary

Estimator validation is separate from closed-loop outcomes. Before any outcome seed is created:

- exact discrete transition must match independent adaptive DOP853 integration within `2e-12`;
- constant-command semigroup and process-covariance construction must pass;
- the scale-normalized discrete observability matrix must have rank 3, smallest singular value
  above `1e-3`, and condition number below `1e5`;
- 601-step nominal covariance replay must remain finite, symmetric within `1e-15`, and have minimum
  eigenvalue greater than `1e-10`;
- one-second delayed updates must match equivalent in-sequence filtering within `1e-13`;
- NIS and offline NEES implementations must match direct solve-based calculations;
- stale, dropout, bias, covariance-underreporting, and forced-divergence fixtures must produce the
  frozen deterministic status and fallback behavior;
- two same-platform estimator replays must have identical trace hashes;
- source/interface inspection must show no truth or evaluator route into online components.

Future closed-loop consistency reporting summarizes each root, not each correlated time step.
NIS uses estimator-available innovations. NEES is evaluator-only. Pointwise chi-square references
are diagnostics; they are not treated as independent repeated tests. Aggregate coverage, error,
rejection, prediction-only, and divergence summaries are reported by arm and stratum.

## 9. Seed contract and inferential unit

Outcome roots are not materialized at this freeze. The derivation is

```text
SeedSequence([master=3003, partition, stratum, replicate, stream])
```

with PCG64DXSM and named streams for initial state, process disturbance, primary measurement,
monitor measurement, fault parameters, and arm order. Partition 31 reserves the pilot; partition
32 reserves a future confirmatory campaign; partition 931 is restricted to non-outcome numerical
fixtures. No seed may be replaced or extended because of an outcome.

The inferential unit and bootstrap unit are the complete four-arm root block. Commands, packets,
state samples, innovations, NIS, NEES, and evaluator times are repeated measurements, not
replicates.

## 10. Small pilot and progression

A separate future task may materialize exactly 64 roots in each of seven strata:

```text
7 strata × 64 roots × 4 arms = 1,792 episodes.
```

The pilot is design-validation evidence, not a confirmatory efficacy test. It reports every
prespecified endpoint but performs no primary hypothesis decision and cannot progress based on
benefit direction or nominal significance.

Progression requires all of the following:

- exact complete 448-block/1,792-episode manifest and no duplicate or replacement cell;
- historical evidence integrity, seed disjointness, interface leakage, numerical, observability,
  covariance, deterministic replay, and publication/privacy gates all pass;
- every scheduled four-arm pilot block is complete;
- no unclassified estimator, controller, invalid-action, or numerical failure;
- independent evaluator and online information boundaries remain intact;
- pilot nuisance information supports at least one predeclared confirmatory candidate under the
  frozen conservative power rule.

Observed arm-effect direction is not a progression criterion. Failure of any critical gate blocks
progression and remains in the record.

## 11. Future confirmatory size and analysis

Candidate roots per stratum are fixed at `250, 500, 750, 1000, 1500`. Power planning uses 20,000
paired risk-difference simulations from seed `300317`, exact equal stratum weights, paired-normal
planning bounds, conservative 95% upper confidence bounds for pilot per-stratum discordance, H1
effect `-0.02`, and H2 true difference zero against margin `-0.03`. The observed pilot effect is not
inserted into the power alternative. The planning approximation is not substituted for the frozen
paired bootstrap in the future outcome analysis.
The smallest candidate whose lower Monte Carlo 95% bound is at least 95% for both marginal H1 and
H2 power may be selected. If none passes, no confirmatory freeze is permitted; the candidate grid
is not enlarged after viewing outcomes.

A future confirmation uses a stratified paired percentile bootstrap with 50,000 replicates from
seed `300318`, resampling complete roots within strata and retaining weight `1/7`. H1 then H2 use
the serial gate above. Four secondary one-sided tests form one Holm family at alpha 0.05:

- H3 `RD_analysis_hazard(PS-D) < 0`;
- H4 `RD_analysis_hazard(PD-PS) < 0`;
- H5a `RD_recovery_favorable_180(PD-D) > 0` over faulted strata;
- H5b paired mean restricted unrecovered time `PD-D < 0` over faulted strata.

H5b uses 200,000 sign-randomization draws from seed `300319`. R is descriptive. Estimator
accuracy, NIS/NEES, fault-severity plots, and continuous metrics are secondary or descriptive and
cannot change H1/H2.

Exactly three primary sensitivities are allowed:

1. missing PD coded adverse and missing D coded favorable to D over every scheduled root;
2. physical-hazard-only PD-D analysis;
3. all available D/PD pairs even if R or PS is missing.

No outcome-selected subgroup, threshold, exclusion, transform, retry, or additional sensitivity is
permitted.

## 12. Failure, stopping, and amendment rules

Controller, estimator, invalid-action, or numerical failure produces an adverse-valid episode row:
`analysis_hazard=1`, `sustained_success=0`, recovery `FAILED`, and the specific failure code. It does
not become a collision claim. Outcome-era automatic retries are forbidden. Infrastructure failure
stops execution with partial output retained; it does not authorize a replacement root.

More than 1% incomplete confirmatory blocks overall or in any stratum yields
`inconclusive_invalid`. The pilot requires complete scheduled blocks.

Before outcomes, any critical failure yields `NOT READY`. After outcome materialization, changes to
population, arms, dynamics, observations, estimator equations, initialization, `Q/R`, timestamps,
innovation/divergence rules, gate, policy, endpoints, recovery, margins, multiplicity, sample size,
or seed derivation abandon that version. A separately documented amendment must use untouched
seeds. Criteria may not be weakened to obtain readiness.
