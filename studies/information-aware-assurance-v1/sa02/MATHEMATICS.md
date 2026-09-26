# SA02 bounded observation consistency

## Scope and inherited dynamics

This module enhances the same KRI Space Autonomy programme. The unchanged SA01
planar HCW model, research geometry, acceleration limit, actuator-effectiveness
interval [0.8,1], component disturbance bounds 1e-5 m/s2, command clock, baseline
controller and finite three-second coasting obligation control this phase. It
adds observation conditioning. No sensor hardware, probabilistic calibration,
active sensing policy, improved recovery theorem or mission superiority is claimed.
The parent source identities are in source-map.json.

## Observation and fault contract

Let z=(x,y,vx,vy) and let b=(cx,cy,br,bb) be constant latent parameters within
one declared hypothesis. For actual acquisition time tau, the modeled readings
satisfy

```
r_read = norm((x(tau),y(tau)) + alpha(tau)*(cx,cy)) + alpha(tau)*br + er
beta_read = wrap(atan2(y(tau)+alpha(tau)*cy, x(tau)+alpha(tau)*cx)
                 + alpha(tau)*bb + eb)
```

The represented packet value is interpreted as its decimal serialization, as in
SA01's rational conversion. The total errors er and eb include numerical encoding
and are assumed bounded by 0.01 m and 0.001 rad by default. They are not measured,
estimated from residuals or derived from covariance. Common position offsets
are applied before both sensor functions, so the channel errors are dependent.
No independence, zero mean, Gaussian model or averaging reduction is used.

The default union permits zero bias; a persistent range bias in [-0.4,0.4] m;
persistent simultaneous common-position offsets in [-0.5,0.5] m per coordinate,
range bias in [-0.4,0.4] m and bearing bias in [-0.02,0.02] rad; and the same
combination active only on the declared interval [5000,10000) ms. The last is an
allowed schedule inherited from the engineering fixture family, not an inferred
fault onset. The estimator receives all hypotheses, never the selected injected
fault. Users may declare another supported fixed window before a run.
Arbitrary unknown fault switches, bias random walks and calibration drift are
outside this finite hypothesis contract. The constant latent bias remains in the
augmented state even while its window is inactive. Retained boxes express
possibility, not probabilities; nested hypotheses can remain indistinguishable.

Clock uncertainty is independently bounded for each packet, without claiming
independent stochastic errors. With reported time s, allowance delta and
availability a, tau belongs to [max(0,s-delta),min(s+delta,a)]. Initialization
at time zero precedes all sensor acquisition. A packet is usable only after
availability; a future packet is neither stored nor used to narrow the present.
Default delta is at most 2 ms. The model requires actual acquisition to obey this
bound and to precede availability. It cannot detect every false timestamp.

## Continuous propagation and uncertain acquisition time

Known applied command history must cover initialization to the decision epoch
without gaps or overlaps. Previously accepted history is immutable. Interval
propagation calls the pinned SA01 rational Picard/Euler inclusion, split at every
command boundary with steps no greater than 50 ms. It supports the declared
bounded, possibly time-varying effectiveness and disturbance. The analytical
inclusion and dimensionless coordinate scaling remain those of SA01.

An unconditional propagation from the original prior bounds the velocity of every
admitted trajectory up to the current decision time. For a packet interval [l,q],
let Vx,Vy be the corresponding valid bounds (the implementation conservatively
uses the maxima over the complete known past). For j in {x,y},

```
abs(p_j(q) - p_j(tau)) <= Vj*(q-l)/1000 = Dj.
```

Thus the unknown acquisition position is enclosed by the endpoint position plus
[-Dj,Dj]. This inequality remains valid for overlapping or out-of-order packet
time intervals. It does not propagate a future truth state backward or credit
information before its arrival. A packet crossing the permitted fault-window
boundary creates both active and inactive branches. Dropping the correlation
between exact acquisition time and that mode enlarges the set, rather than
claiming exact attainability.

Processing is ordered by latest possible acquisition time, with deterministic ties.
On-time arrivals extend the previous conditioned epoch. Inserting an older packet
replays all retained constraints from the original prior, using the known command
history. Prediction to the decision and to a separately supplied application queue
contains no extra sensor update. Application prediction is limited to the existing
0-200 ms queue interface. Unknown queued actions invalidate that prediction.

## Necessary interval constraints

The eight-dimensional boxes retain position, velocity and constant bias bounds.
For each packet, interval calculations enclose the possible biased Cartesian
position at acquisition. A range packet restricts its radius and the range-bias
interval. From r in [rlo,rhi] and the other coordinate interval Y,

```
X squared belongs to [max(0,rlo squared - max(Y squared)),
                      rhi squared - min(Y squared)].
```

Signed Cartesian contraction uses these necessary squared-distance bounds. When
both signs remain possible, their interval hull is retained. For a bearing packet,
theta belongs to beta_read - alpha*bb + [-error,error]. Sine and cosine are bounded
without a discontinuous angle subtraction, so +/-pi wrap is included. If R bounds
the nonnegative norm, acquisition coordinates belong to R*cos(theta), R*sin(theta).
An interval containing the origin provides no justified atan2 observation; that
bearing constraint is omitted with an explicit degeneracy diagnostic.

Moving these coordinate restrictions back to the endpoint produces constraints
on x(q)+alpha*cx and y(q)+alpha*cy enlarged by Dj. The exact-rational linear
contractor isolates each variable against the other variables' interval sum.
Every contraction is necessary, not sufficient for an attainable full history.
Latent offsets are never resampled or assigned independent weights per packet.

Square roots are enclosed by integer-square-root calculations on a 1e-12 grid;
endpoint squares check the direction of the bounds. Trigonometric enclosures use
rational Taylor polynomials at the interval midpoint, Lagrange remainders of
orders 37 (sine) and 38 (cosine), and the global 1-Lipschitz bound over the radius.
Large arguments or wide intervals conservatively return [-1,1]. Other interval
arithmetic is rational; no floating-point trigonometric call decides a set exclusion.

## Outer-containment argument

Assume the initial state is in the supplied prior, the actual dynamics and applied
history satisfy the contract, and at least one declared fault hypothesis with a
single coherent latent bias explains the observations within their time/error bounds.
Initial subdivision covers that hypothesis's full parameter domain. Induction over
propagation and observation updates then gives an augmented box containing the
actual state and bias: continuous propagation contains its trajectory, the time
inflation contains its actual acquisition position, and every necessary measurement
constraint retains it. Branching preserves both permitted timing modes. Outward
hull coarsening and projection preserve inclusion. Intersecting the current output
with the independently propagated unconditional prior also preserves inclusion.

This establishes a conditional outer-containment argument for the mathematical
model. It is not an exact characterization of the feasible histories, a proof-assistant
verification, physical calibration or an unconditional operational guarantee.

## Correlation, resources and validity

The finite union retains some state/bias and fault-mode correlation through separate
boxes. Axis-aligned propagation, projection and hull coarsening lose correlation and
may retain impossible state/bias combinations. The implementation never ranks boxes
by weight. At the configured cell cap it merges boxes only within the same hypothesis;
it refuses a configuration that cannot represent every initial hypothesis. The default
is at most 16 retained cells, 128 accepted packets, 256 normalized command segments,
a 30 s episode and 100000 counted integration/contraction work units per update.
Input batches have a separate 512-packet cap; trigonometric caching has 1024 entries.
These are algorithmic size/work limits, not measured byte budgets or processor WCET.

On missing or stale measurements, the last valid constraints are propagated. At a
packet limit, new observations are explicitly unassimilated. On work exhaustion,
only a fully propagated unconditional prior can be returned as fallback. Partial
filtering is not promoted. Unsupported packets and numerical/history failures are
visible; contradictory data latch inconsistency until a separately initialized
observer is provided. The previous dynamics prior remains available for diagnosis.
An empty consistency set means data or assumptions conflict, never that the vehicle
has no physical state. A small unmodeled bias can produce a nonempty set excluding
truth without being detected; a retained fixture demonstrates this limitation.

## Downstream use

Every estimate has outer-only semantics. Its hull can feed the existing finite-prefix
checker as a sufficient set after the validity filter in bridge.py. The legacy
Uncertainty kind is used only as an internal mathematical box adapter; the measurement
status explicitly identifies the SA02 outer projection, and the new estimate and
contract identity accompany the record. Missing/stale predictions and resource-only
fallbacks can be used only while the independent dynamics assumptions remain valid.
Unsupported packets, inconsistency and unavailable bounds do not receive a positive
checking input. The three-second finite coast remains conditional and may expire.

No corner of an outer box is supplied as an attainable witness. The negative-input
interface deliberately rejects all SA02 estimates. Failure to find an action for
the outer set is unresolved; it is not proof that the actual compatible histories
have no common action. Constructing certified compatible witnesses is separate work.

## Independent validation and execution boundary

oracle.py enumerates exact vertices of bounded two-/three-dimensional linear
polytopes using separately written rational Gaussian elimination. It imports no
production interval, propagation or observation code. Static repeated-bias and
constant-velocity measurement histories test the interval contractor against this
reference, including an outer-box corner that is not feasible. Polar boundary tests
and independent binary64 trajectories give additional numerical corroboration.
They do not turn the small linear oracle into a second full spacecraft estimator.

sa02/runtime.py is a separately identified adaptation of SA01's loop. The baseline,
plant, input authority, modeled timing/energy and safety/dwell definitions are unchanged.
Its observation construction is offline simulation computation. Real observer-call
host times are measured separately and never substituted for the existing 50 ms
modeled pipeline. No target timing, energy saving or physically timely dispatch is
established by a simulation completing. All missing sets, exclusions, assumption
violations, protection gaps and unsuccessful mission dwell remain reported.

## Additional independent and adversarial checks

The small reference also encodes the augmented constant-input HCW matrix directly,
without importing the production propagation matrix or routines. A degree-28
rational matrix-series sum at t <= 3 s encloses its remainder using

    ||z0||inf * (L*t)^29 / 29! / (1 - L*t/30),

where L is the independently calculated matrix infinity norm and L*t/30 < 1.
The geometric tail bound follows by bounding all successive term ratios by
L*t/30. These reference intervals are checked inside the production enclosures
for eight constant-input cases. This is additional mathematical/numerical
validation, not a second complete sensor-history implementation. An exact static
range-plus-bias specialization also checks the full Observer against independently
enumerated feasible vertices, not just the stand-alone linear contractor.

Contracts copy supplied hypothesis, bias and window sequences into immutable
tuples. Estimate schemas and scopes are validated before downstream use.
A resource failure cannot clear a previously latched inconsistency; a rejected
contradictory history remains unusable until explicit reinitialization. Regression
tests first reproduced violations of these interface rules and then checked the
corrections. No earlier stage source or outcome was changed.

The development evaluator checks whether the configured offset schedule has an
exact member in the declared fault family independently of the fixture name.
This evaluation-only fact is not communicated to the observer. Absence of an
exact offset member is not a general proof of observation inconsistency: bounded
measurement residuals and other possible states may mask a fault. The inherited
`assumptions_valid` and time-coverage fields explicitly identify their dynamics
scope; sensor-family support is reported separately. No whole-system protection
claim can be inferred from a dynamics-only coverage count.
