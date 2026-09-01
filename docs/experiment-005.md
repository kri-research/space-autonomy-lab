# Experiment 005: nonlinear two-body truth foundation

## Status

This is a prospective, pre-outcome foundation. It executes no Experiment 005 calibration, pilot,
or confirmatory scientific cells and makes no model-fidelity outcome claim. Experiment 001-004
artifacts remain byte-protected. No Experiment 004 outcome was used to choose the Experiment 005
geometry, command bounds, numerical tolerances, challenge cases, thresholds, or future sample size.

The readiness question is narrower: can the Experiment 004 planar HCW controller/estimator and
runtime-assurance mechanics be connected, without hidden substitutions, to physical truth generated
by nonlinear central-gravity chief/deputy dynamics?

## Truth and online-model separation

Physical truth is a 12-state inertial Cartesian system: three-position and three-velocity states for
both chief and deputy. Each body receives Earth central gravity. The chief starts on the same ideal
400 km circular reference used by Experiment 004. Initial deputy states are planar in the chief
LVLH frame, but truth propagation remains full three-dimensional translation.

The online navigation filters, controller, and estimated-geometry monitor continue to use the
Experiment 004 planar HCW model. This is intentional. The physical truth model is never presented as
the estimator model, and truth-versus-HCW residuals are recorded as model mismatch rather than
corrected away.

The LVLH basis is radial-outward, prograde along-track, and orbit-normal. The frame conversion uses

```text
r_deputy = r_chief + C_I<-L rho_L
v_deputy = v_chief + C_I<-L (rho_dot_L + omega_L x rho_L)
```

and the inverse subtracts the rotating-frame term. A held radial/along-track command is held in LVLH
components for one second and remapped with the instantaneous chief basis at every integration
stage; it is not treated as a constant inertial vector.

## Production propagation and independent reference

Production truth uses deterministic fixed-step classical RK4 with steps no longer than 0.1 s and
exact splitting at control-interval endpoints. Euler is not used. Independent numerical validation
uses SciPy DOP853 with relative tolerance `1e-12`, position absolute tolerance `1e-9 m`, and velocity
absolute tolerance `1e-12 m/s`. Prospective RK4 acceptance is `1e-5 m` position and `1e-8 m/s`
velocity against that reference across one-, 60-, and 600-second deterministic mechanics fixtures.

Validation also checks frame round trips at four orbital phases, command norm/axis mapping,
right-handed orthonormal bases, circular radius and speed, specific energy, angular momentum, and a
coincident deputy invariant.

## Physics envelope and HCW mismatch

The local-limit envelope comes only from Experiment 004 inputs:

- radial position `[-10, +10] m`, the widest approach-corridor bound;
- along-track position `[-100, -27] m`, from approach start through the outer hold ellipse boundary;
- per-axis relative speed `[-0.14, +0.14] m/s`, derived as the larger of the initial approach speed
  and hold-speed bound plus one maximum one-second command increment;
- LVLH command norm no greater than `0.02 m/s^2`;
- one-second matched nonlinear/HCW intervals.

Maximum position and velocity mismatch and mismatch normalized by the 10 m keep-out radius are
reported descriptively. There is deliberately no favorable absolute mismatch threshold. A separate
scale test at factors 1, 1/2, and 1/4 requires the expected local quadratic convergence structure;
that structural gate detects frame/sign defects without redefining ordinary nonlinear-minus-linear
mismatch as failure.

## Independent truth-space event geometry

Physical events are evaluated offline from nonlinear inertial truth transformed back to LVLH. No
physical trajectory or event evidence is returned to online components. Collision and keep-out
sets remain closed three-dimensional separation thresholds.

A validity review identified that the historical Experiment 004 corridor helper classifies every
point outside its along-track interval as non-departed. Historical code and results are not changed.
Experiment 005 instead prospectively defines admissible planar position as the union of the closed
tapered approach corridor and the closed hold ellipse. Exiting below `-100 m`, above `-27 m`, or
radially outside both sets therefore fails closed. Truth-space fixtures cover interior collision,
closed boundaries, radial departure, both longitudinal exits, hold admission, and planarity.

## Prospective seed domains

Experiment 005 uses master seed 5005 with disjoint partition codes:

- 51: future mechanics/metric calibration;
- 52: future non-inferential design-validation pilot;
- 53: future confirmatory work;
- 951: deterministic non-outcome fixtures.

Partitions 51-53 are unmaterialized. There is no pilot or confirmatory generator, case matrix,
hypothesis, threshold, or sample size at foundation freeze.

## Future execution architecture

The foundation provides only outcome-blind integer fixtures through the future campaign execution
path. The path uses a process pool, a frozen ordered cell schedule, campaign-bound content-hashed
shards, no-clobber atomic publication, file and directory synchronization where supported, an
exclusive campaign lock, canonical final assembly, and restart of validated missing cells only.
Corrupt, foreign, noncanonical, or conflicting evidence fails closed and is never silently
recomputed. Fixture tests prove fresh serial/parallel byte equivalence, interrupted serial to
parallel continuation, completed-shard reuse, and corrupt-shard rejection.

## Evidence boundary and next task

Foundation readiness is mechanical and numerical, not a scientific finding. The checked-in
validation evidence, freeze manifest, and readiness record bind source hashes, the full protected
base snapshot, historical Experiment 002-004 result verifiers, dependency identity, seed absence,
privacy/provenance/secrets scanning, phase-appropriate tests, Ruff, compilation, and the stable
product gate.

If and only if all gates pass, the next task is to design a separate non-inferential transfer pilot.
It may use partition 51 prospectively, must freeze its cases and sample count before enabling
partition 52, and must leave partition 53 untouched.
