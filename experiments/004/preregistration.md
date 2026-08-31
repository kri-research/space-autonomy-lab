# Experiment 004 planar HCW foundation preregistration

_Pre-outcome foundation; no Experiment 004 pilot or confirmatory outcomes materialized_

## Evidence boundary and design lesson

Experiment 004 is a new planar relative-motion foundation, not a reinterpretation of earlier
campaigns. The Experiment 002 final direct-measurement campaign was favorable under its frozen
synthetic design. The Experiment 003 estimator-in-loop final campaign was valid and reproducible
but inconclusive: D and PD had zero `analysis_hazard` events in every E0-E6 stratum, the H1 PD-D
estimate was 0 with a 95% interval of `[0, 0]`, H2 was not tested because its gate remained closed,
and descriptive sustained success for PD-D was -0.184 overall, with large negative differences in
the monitor-only and shared-bias E5/E6 strata. These facts remain historical evidence and are not
optimized away.

The foundation question is whether a planar orbital plant, navigation stack, vector control
contract, independent geometry evaluator, and isolated seed domains can support a reproducible,
non-inferential design-validation pilot. It does not test an architecture benefit. No primary
aggregate outcome, arm family, effect threshold, confirmatory hypothesis, or confirmatory sample
size is frozen here.

## Orbital reference and coordinate convention

The chief follows a synthetic circular Earth reference orbit. The frozen constants are Earth
`mu = 3.986004418e14 m^3/s^2` and geocentric reference radius `6,778,137 m`, described as 400 km
above the declared `6,378,137 m` equatorial reference radius. Mean motion is derived as
`n = sqrt(mu / r^3) = 0.0011313666536110223 rad/s`; the corresponding period is about 5,553.62 s.

The target-centered frame rotates with the chief. `+x` is radial outward from Earth and `+y` is
along-track in the chief velocity direction. State and commanded acceleration are

```text
[x_radial_m, y_alongtrack_m, vx_radial_mps, vy_alongtrack_mps]
[ax_radial_mps2, ay_alongtrack_mps2]
```

The governing equations are

```text
xddot = 3 n^2 x + 2 n ydot + ax
yddot = -2 n xdot + ay
```

Each constant-command interval uses the exact zero-order-hold transition obtained from one
augmented matrix exponential. An independent analytical HCW transition/input matrix and an
independently coded scalar DOP853 integration are validation references. Euler propagation is not
used. Disturbance covariance represents independent piecewise-constant two-axis acceleration
draws every 0.25 s, each with standard deviation `0.0005 m/s^2`; it is not a continuous white-noise
spectral density.

HCW is a local linear relative-motion approximation for a circular chief orbit. It is not full
nonlinear orbital mechanics, does not include eccentric-orbit effects, and omits cross-track and
attitude dynamics.

## Frozen planar geometry

The target is at the origin. The nominal chaser state begins at `(x, y) = (0, -100) m` with
velocity `(0, +0.12) m/s`, approaching in the positive along-track direction. The exterior hold
point is `(0, -30) m`.

- Collision is the closed center-to-center disk `sqrt(x^2 + y^2) <= 2 m`.
- Unauthorized keep-out entry is the closed disk `sqrt(x^2 + y^2) <= 10 m`.
- No terminal keep-out entry is authorized in this hold-point study.
- The V-bar corridor covers `-100 <= y <= -30 m`; radial halfwidth tapers linearly from 10 m to
  3 m.
- The hold-position region is an ellipse with radial and along-track halfwidths 2 m and 3 m,
  combined with speed `<= 0.05 m/s`.
- Hold acquisition requires 60 continuous seconds wholly inside both position and speed limits.

Geometry is evaluated on the exact HCW arc and every arc is split at intervals no longer than one
second. Endpoint chords are not used. Boundary contact counts as collision or keep-out entry.
Collision, keep-out entry, corridor departure, hold acquisition, hold dwell, and safe incomplete
mission status remain separate fields.

## Navigation and packet semantics

The filter state is the four-state HCW state; no one-dimensional filter is reused. Each primary or
monitor packet contains Cartesian position and velocity in the frozen state order, source and
receipt timestamps, a sequence identity, and a finite symmetric positive-definite 4 by 4 reported
covariance. Position-position covariance entries have units `m^2`, position-velocity entries have
units `m^2/s`, and velocity-velocity entries have units `m^2/s^2`.

The measurement matrix is `H = I4`. Nominal per-axis standard deviations are 0.25 m for position and
0.01 m/s for velocity. Quantization steps are 0.02 m and 0.002 m/s, with quantization variance
included as `q^2/12`. The sampled full-state and position-only HCW systems must both pass scaled
observability checks at the frozen one-second interval.

The filter predicts with the exact discrete HCW transition and executed vector command, updates
with linear solves and the Joseph covariance form, and supports a maximum one-second fixed lag.
Filter epochs are integer command ticks. A packet measured exactly one command period earlier is
admissible; older, future, duplicate, off-grid, nonfinite, or invalid-covariance packets fail closed.
Same-epoch packets are replayed in sequence-identity order. The normalized-innovation-squared
rejection threshold is the frozen four-degree-of-freedom 0.999 quantile
`18.46682695290317`. Covariance symmetry, positive-semidefinite tolerance, trace, innovation
conditioning, state limits, prediction-only age, and consecutive rejection limits are explicit.

Primary and monitor channels have separate packet construction and filter instances. Bias,
dropout, stale-packet, and covariance-underreporting mechanisms can affect primary only, monitor
only, or both channels. Fault identity, schedule, severity, realized disturbance, physical state,
and evaluator output are not packet fields.

## Vector control and monitor foundation

Experiment 004 defines an additive vector research contract rather than forcing the stable scalar
product contract into two dimensions. The deterministic reference is a bounded discrete LQR hold
controller using the exact one-second HCW matrices, state cost diagonal `[1, 1, 100, 100]`, control
cost diagonal `[100000, 100000]`, and a Euclidean command limit of `0.02 m/s^2`. Its identity is
derived deterministically from those frozen inputs. It is a numerical and mission-feasibility
reference, not a fitted or learned policy.

A bounded one-step estimated-geometry monitor is available for design validation. It receives a
navigation snapshot, covariance and health, the proposed vector command, and expected controller
identity. It does not receive physical state or evaluator outputs. It uses a three-standard-
deviation position-uncertainty inflation and the exact estimated HCW arc. This screen is not formal
reachability analysis or a flight-safety guarantee. The future pilot must report monitor behavior
separately from physical outcomes.

## Independent evaluator and outcome domains

The physical evaluator imports neither controller nor filter implementations and returns no data
to online components. Event classification uses only exact physical arcs and frozen geometry.
Technical diagnostics are joined only after physical evaluation. The following domains remain
separate:

1. physical geometry: collision, unauthorized keep-out entry, corridor departure and minimum
   separation;
2. mission performance: hold acquisition, contiguous dwell, hold loss and safe incomplete status;
3. primary-estimator fault;
4. monitor-estimator or monitor-logic fault;
5. shared-cause fault;
6. controller, invalid-action or numerical failure.

No aggregate `analysis_hazard` is defined by this foundation. A later study may freeze an aggregate
only after the non-inferential pilot demonstrates correct event capability and after its scientific
question is independently justified. Hazard or success discordance between configurations is not a
foundation readiness criterion.

## Prospective seed partitions

Experiment 004 uses PCG64DXSM and

```text
SeedSequence([4004, partition, geometry_case, fault_case, replicate, stream])
```

The reserved domains are:

- 41: dynamics and metric calibration;
- 42: future controller or policy fitting, unused by the deterministic reference;
- 43: design-validation pilot;
- 44: future confirmatory work, with no hypothesis, size, or generator;
- 941: deterministic non-outcome test fixtures.

Named streams separately cover initial state, radial and along-track process disturbance, primary
and monitor measurement, fault parameters, actuator uncertainty, and configuration run order.
Experiment 004 uses a distinct master seed and root namespace from Experiments 001-003.
Replacement, outcome-dependent extension, and outcome-dependent threshold selection are forbidden.
No partition 41-44 seeds or results are materialized in this foundation.

## Fail-closed foundation gates

Readiness requires all of the following before any pilot generator may be added:

1. augmented-exponential dynamics agreement with analytical HCW matrices and scalar DOP853;
2. state/action units, signs, orbital reference, semigroup behavior and unforced invariant checks;
3. exact-arc collision, closed-boundary, keep-out, corridor and hold-dwell fixtures;
4. full and position-only observability checks;
5. process and posterior covariance finite, symmetric and positive-semidefinite checks;
6. fixed-lag chronological equivalence, deterministic replay and divergence behavior;
7. online-interface leakage scan;
8. separate physical, mission, estimator, monitor and shared-cause status fields;
9. partition uniqueness, absence and historical disjointness;
10. locked dependency/runtime identity;
11. byte identity for every file tracked at merged main commit `bef9bb4`, including all frozen
    Experiment 001-003 evidence;
12. current Experiment 002 final and Experiment 003 pilot/final freeze and result verifiers;
13. repository tests with explicit outcome-era phase exclusions, Experiment 004 tests, Ruff,
    compileall, stable gate, whitespace check, and publication/privacy scan.

The deterministic 600-second controller fixture is only a numerical and mission-feasibility check.
It is not an Experiment 004 outcome, estimate, or scientific finding.

## Bounded next task

The next task is a separate non-inferential design-validation pilot design. It must use partition 41
only to freeze a symmetric scenario/severity grid and metric implementation; freeze the pilot
sample count without reference to desired arm differences; include nominal, forced-event,
primary-only, monitor-only, shared-channel and actuation cases; validate event/fault activation,
complete blocks and deterministic replay; and only then add a write-once partition-43 generator.
It must not materialize partition 44 or perform confirmatory inference.
