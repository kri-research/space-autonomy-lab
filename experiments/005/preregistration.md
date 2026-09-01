# Experiment 005 nonlinear-truth foundation preregistration

_Pre-outcome model-fidelity transfer foundation; no Experiment 005 scientific partition executed_

## Scientific question and non-question

The future Experiment 005 programme asks whether the Experiment 004 planar HCW autonomy and
runtime-assurance architecture remains mechanically valid when chief/deputy physical truth is
nonlinear central-gravity orbital motion while the online controller and estimators retain their
HCW assumptions.

This foundation does not estimate an architecture benefit, fault effect, event rate, success rate,
or nonlinear-versus-linear performance difference. It does not define an inferential arm family,
challenge matrix, aggregate endpoint, effect threshold, pilot size, confirmatory hypothesis, or
confirmatory size. No Experiment 004 outcome value may be used to choose any of those quantities.

## Frozen model boundary

### Physical truth

The truth state is

```text
[chief_r_I(3), chief_v_I(3), deputy_r_I(3), deputy_v_I(3)]
```

in metres and metres per second. Both bodies obey

```text
r_ddot = -mu r / |r|^3
```

and the deputy additionally receives commanded acceleration. The frozen Earth research constant is
`mu = 3.986004418e14 m^3/s^2`. The ideal chief begins equatorial, prograde, and circular at geocentric
radius `6,778,137 m`, described consistently with Experiment 004 as 400 km above the declared
`6,378,137 m` equatorial reference radius. These are testbed conventions, not an ephemeris or a
high-fidelity Earth model. Perturbations, oblateness, drag, third bodies, attitude, plume effects,
and 6-DoF dynamics are outside this step.

Initial relative states and commands are planar, with zero cross-track components, but the inertial
truth integrator carries all translational axes.

### LVLH transforms

With `C_I<-L = [e_radial, e_alongtrack, e_normal]` and instantaneous LVLH angular velocity `omega`,

```text
Delta_r_I = C_I<-L rho_L
Delta_v_I = C_I<-L (rho_dot_L + omega_L x rho_L)
```

The inverse is

```text
rho_L = C_I<-L^T Delta_r_I
rho_dot_L = C_I<-L^T Delta_v_I - omega_L x rho_L.
```

Round-trip fixtures include planar and nonplanar states at four orbital phases. Position and
velocity acceptance are `5e-9 m` and `5e-12 m/s`; orthonormality and right-handedness acceptance is
`5e-15` absolute.

### Online model

The two navigation filters, bounded LQR controller, and estimated-geometry monitor retain the
frozen Experiment 004 planar HCW implementation. Their state remains
`[x, y, vx, vy]`. The truth model and its event evaluator are offline. Physical truth, event
classifications, and truth/model discrepancy are prohibited online inputs.

### Command semantics

The transferred bound is on commanded LVLH acceleration: norm no greater than `0.02 m/s^2`.
A command is constant in LVLH components over each one-second control interval. Its inertial vector
is recomputed from the instantaneous chief frame at every RK4 stage, so a radial command rotates in
inertial space. Future disturbance, actuator-effectiveness, bias, and saturation semantics are not
frozen here and may not be inferred from the command bound.

## Numerical production contract

Production propagation is bounded fixed-step classical RK4 with maximum step `0.1 s`, split exactly
at every control endpoint. Euler is forbidden as physical truth. The independent reference is
DOP853 with `rtol=1e-12`, position `atol=1e-9 m`, velocity `atol=1e-12 m/s`, and maximum reference
step `0.25 s`.

Prospective production acceptance across deterministic one-, 60-, and 600-second fixtures is:

- maximum inertial position norm discrepancy no greater than `1e-5 m`;
- maximum inertial velocity norm discrepancy no greater than `1e-8 m/s`.

The 600-second unforced circular fixture also requires:

- circular-radius error no greater than `1e-4 m`;
- circular-speed error no greater than `1e-7 m/s`;
- specific-energy and angular-momentum relative drift no greater than `1e-11`;
- exactly coincident unforced chief/deputy states remain equal.

## Prospective local-limit envelope

The local nonlinear-versus-HCW checks use only Experiment 004 geometry and command inputs:

```text
x in {-10, +10} m
y in {-100, -27} m
vx, vy in {-0.14, +0.14} m/s
u in {zero, +/- maximum radial, +/- maximum along-track}
duration = 1 s
```

The speed magnitude derives prospectively as

```text
max(0.12 m/s initial approach speed, 0.05 m/s hold bound)
+ 0.02 m/s^2 * 1 s = 0.14 m/s.
```

For all 80 corners, the evidence reports maximum nonlinear-minus-HCW position and velocity mismatch
and position mismatch divided by the 10 m keep-out radius. No absolute mismatch value is an
acceptance gate. A 60-second unforced state scaled by 1, 1/2, and 1/4 must show finite, monotonic
mismatch reduction with observed order between 1.5 and 2.5. This is a structural local-linearization
check, not an attempt to force small mismatch.

## Independent event geometry

Collision and keep-out entry are closed sets based on full three-dimensional truth separation at
2 m and 10 m. Events are evaluated on nonlinear arcs split at no more than one second, with bounded
continuous-time extrema rather than endpoint chords.

The historical Experiment 004 corridor implementation has an out-of-range false-safe behavior. It
is retained byte-for-byte as historical evidence and remains the online monitor's stated model.
The independent Experiment 005 physical evaluator instead freezes the admissible planar position
set as the union of:

1. the closed tapered approach corridor, `-100 <= y <= -30 m`, radial halfwidth 10 m to 3 m; and
2. the closed hold ellipse centred at `(0, -30) m`, radial/along-track halfwidths `(2, 3) m`.

This makes exits below `-100 m`, above `-27 m`, and outside both radial bounds fail closed. Fixtures
cover an interior collision with safe endpoints, closed collision contact, safe approach, radial
exit, both longitudinal exits, hold admission, and zero cross-track preservation.

## Seed reservation

Randomized future work will use PCG64DXSM and

```text
SeedSequence([5005, partition, geometry_case, challenge_case, replicate, stream]).
```

Reserved partitions are 51 for mechanics/metric calibration, 52 for a future design-validation
pilot, 53 for future confirmatory work, and 951 for deterministic non-outcome fixtures. Named streams
separate initial truth, mechanics perturbation, primary and monitor navigation, challenge
parameters, actuation, and cell order. The root namespace is `experiment005:`.

Partitions 51, 52, and 53 remain unmaterialized. No generator for them is available at foundation.
Replacement, extension, and design or threshold selection based on Experiment 004 outcomes are
forbidden.

## Future campaign execution contract

Only deterministic partition-951 fixtures exercise the execution architecture now. Before any
future scientific cell runner may be enabled, the same path must retain:

1. process-based parallelism when worker count exceeds one;
2. a contiguous frozen canonical cell schedule and canonical within-cell order;
3. a campaign identity bound to the ordered schedule;
4. one canonical, content-hashed shard per frozen cell;
5. same-directory no-clobber atomic publication, file synchronization, and directory
   synchronization where supported;
6. an exclusive campaign lock, with stale lock fail-closed review;
7. complete shard validation before worker submission;
8. restart of missing frozen cells only, never valid completed cells;
9. corrupt, foreign, unexpected, noncanonical, duplicate, or conflicting evidence failing closed;
10. canonical final assembly independent of process completion order.

Foundation fixtures must prove fresh serial/parallel byte equivalence, interrupted serial followed
by parallel continuation, exact completed-shard reuse, and corrupt-shard rejection. They access no
scientific outcome partition.

## Fail-closed foundation gates

Readiness requires all of the following:

1. frame round trips including rotating velocity terms and nonplanar fixtures;
2. LVLH command axis, norm, round-trip, and inertial-rotation checks;
3. fixed-step RK4 agreement with independent DOP853;
4. circular-orbit, energy, angular-momentum, and coincident-state invariants;
5. independent nonlinear truth-space event fixtures including both corridor ends;
6. complete descriptive mismatch over the prospective envelope and quadratic local-limit scaling;
7. a deterministic two-filter/controller/monitor mechanics fixture with explicit one-step
   truth-versus-HCW residuals and no mission outcome evaluation;
8. online/offline source-boundary checks;
9. deterministic process-parallel, restart, atomicity, lock, and corruption fixtures;
10. disjoint seed domains and absence of partitions 51-53 and all Experiment 005 result paths;
11. byte identity for every file tracked at merged main `ce50129`, except the sole phase-aware CI
    amendment; the protected snapshot includes all historical Experiment 001-004 bytes/results;
12. current Experiment 002, Experiment 003 pilot/final, and Experiment 004 closeout verifiers;
13. exact runtime/dependency identity, focused tests, phase-appropriate full tests, Ruff,
    compileall, stable gate, whitespace, and tracked-plus-untracked privacy/provenance/secrets scan.

Any failed scientific gate produces `NOT_READY` with the first smallest blocker. `READY` may only be
written after every gate passes.

## Bounded next task

If ready, design one separate non-inferential model-fidelity transfer pilot. Only partition 51 may be
used for prospective mechanics/metric calibration. Freeze cases and sample count before enabling
partition 52. Leave partition 53 unmaterialized, with no hypothesis or size, and do not infer design
choices from Experiment 004 outcomes.
