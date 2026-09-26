# SA01 reference operating contract

## Scope

Version `iaa-reference/1` is a simulation-only engineering foundation for the existing
KRI Space Autonomy programme. It has no physical output driver. These fixtures are
neither a mission specification nor a new confirmatory comparison. No flight safety,
novel safety-filter theorem, hardware timing or operational reliability is claimed.

## Model and geometry

The state is `(x,y,vx,vy)`: radial-outward and along-track position in metres, and
rotating-frame velocity in metres per second, relative to a circular-orbit chief.
The nominal planar HCW equations are

```
x' = vx; y' = vy
vx' = 3 n^2 x + 2 n vy + eta ux + wx
vy' = -2 n vx + eta uy + wy
n = 11/10000 s^-1
```

The permitted commanded acceleration satisfies `ux^2+uy^2 <= (1/50)^2 m^2/s^4`.
The guard assumes `eta in [4/5,1]` and each disturbance component within
`[-1/100000,1/100000] m/s^2`. Both may vary during propagation within these bounds.
Simulation fixtures use constant effectiveness until the declared fault boundary,
then the configured value, and zero disturbance. The fixture using effectiveness
0.2 deliberately violates the guard's model; its later protection is not credited.
Attitude, eccentric chief motion, nonplanar motion, unmodeled gravity and physical
actuator dynamics are excluded. Numerical HCW truth is a separate binary64
closed-form implementation, checked against a matrix-series calculation.

The **closed research position constraint** is `x in [-8,8] m, y in [-60,-30] m`.
This is a generic standoff-inspection box, not an operationally mandated envelope
and not the original experiments' trapezoid/ellipse union. Closed collision and
keep-out disks have radii 2 m and 10 m; contact with either disk is forbidden.
Position containment implies their avoidance, but each is reported separately.
A lost containment proof is not a proof of an actual departure or collision.

The nominal engineering task moves from `(0.5,-45,0,0)` toward `(0,-40,0,0)`.
The declared initial enclosure has position radii 0.02 m and velocity radii
0.005 m/s; it represents supplied initialisation knowledge, not sensor calibration.
Other fixture entry sets are explicitly declared in `iaa/fixtures.py`.
Mission completion requires continuous residence for at least 2 s within 0.35 m
on each position coordinate of the target and speed at most 0.05 m/s.
This dwell condition is not asserted to be a control-invariant terminal set.
The nominal horizon is 30 s; shorter adverse fixtures have their listed horizons.
Every fixture is checked for truth membership in its own initial enclosure.
Initial admissibility and successful protection entry remain separate tests.

## Sensing and information separation

Range is `sqrt(x^2+y^2)` and bearing is `atan2(y,x)` radians, measured in the
same rotating frame. A paired sample is normally acquired every 500 ms. Nominal
availability delays are 40 ms for range and 70 ms for bearing. Packets specify a
reported acquisition timestamp, availability time, timestamp uncertainty (2 ms),
channel, units, frame, sequence and identity. The clock is one simulated clock;
2 ms is a declared timestamp allowance, not an actual clock calibration.

A common Cartesian position bias is applied before producing both measurements;
channel-specific range/bearing biases are added afterward. Dropouts suppress the
specified packet in the fault interval `[start,end)`. Delays affect delivery, not
the state used for acquisition. Invalid timestamps/nonfinite values are rejected.
These mechanisms are configurable and their ground-truth injection labels never
enter the controller interface. Faults are not magically diagnosed by the guard.

The baseline uses only delivered, matched-sequence packets with matching reported
acquisition times. Worst-case packet age must be at most 600 ms. Future, unmatched
and stale packets do not support a proposal. Range/bearing inversion and a backward
position difference produce a **nominal point estimate**, not a certified state set.
The PD proposal uses gains `kp=0.04 s^-2`, `kd=0.4 s^-1`, with a conservative norm
saturation below 0.02 m/s^2. It is an engineering baseline, not a reproduced
state-of-the-art filter or an estimator-validity claim.

The guard receives a separately propagated initial enclosure and known commanded
history only. Its measurement-update status is `unsupported_in_SA01`. It never
replaces that enclosure with the nominal point estimate. SA02 must supply the
measurement-to-set construction. SA03 information-optimal decisions are absent.

## Clock, queue and resource contract

All simulator events use a 10 ms grid. At each 500 ms cycle:

- Normal paired acquisition is at cycle start.
- The decision snapshot is at +100 ms.
- Modeled processing/proposal/checking/dispatch costs are 10/15/20/5 ms.
- A timely result is available at +150 ms and waits until the +200 ms application slot.
- The admitted command is held for 500 ms until the next application slot.

These values are illustrative engineering budgets, not measured execution time.
The zero-order-held prior command continues while a decision is computed. The
guard includes that known queue from snapshot to application, the proposed hold,
and a further 3 s of zero-command coasting. A reply arriving after its application
slot cannot be applied at a shifted time. A lost reply expires into the previously
analysed coast. If the coast's validity time expires, the simulator continues
with explicitly **uncredited zero output**; it does not freeze or reset the plant.
No safe-stop claim follows from a disabled checker or stopped software.

Why 500 ms rather than inheriting the previous one-second interval: this fixture
separates the 70 ms sensing delay, a 50 ms modeled processing path and a 50 ms
arrival-to-dispatch reserve from the control hold. For an entry speed of 0.01 m/s
and acceleration magnitude bounded by 0.03 m/s^2 in the stated local domain, the
first 200 ms displaces at most 0.0026 m. The nominal entry has metres of position
clearance. This scale check motivates the engineering choice; all admitted paths
still undergo the inclusion check. It is not a universal deadline argument. The
near-boundary adverse fixture deliberately lacks that clearance.

A fixed additional observation request at 7250 ms, where inside the fixture
horizon, acquires a new pair 100 ms later and pays normal per-channel costs and
delays. The policy is predeclared, not selected using future truth or information gain.
The modeled work costs are 0.2 mJ per range reading, 0.3 mJ per bearing reading,
and 5 mJ per decision (a 0.1 W active-compute accounting assumption over 50 ms).
The nominal budget is 500 mJ. The adversarial low-budget fixture has 40 mJ.
This is a workload cost model only: it excludes propulsion, baseline avionics,
idle power, radiation mitigation and actual sensor/processor energy. It is not
a spacecraft battery model. Target timing, memory and energy feasibility remain
unmeasured, and the offline reference checker need not meet the modeled 20 ms.

## Analysed protective response

The response is **finite zero-command coasting for at most 3 s**, starting at an
admitted command's expiry. It buys an explicitly bounded interval for a replacement
decision; it is not braking, return-to-target or indefinite recovery. Its entry
condition is that the entire prior enclosure, queue, hold and coasting tube satisfy
the research position constraint and keep-out separation under the declared model.
When a proposed manoeuvre fails that sufficient check, the same checker may admit
a zero-command replacement. Failure of both checks is unresolved, never physical
impossibility. When the checker is unsupported there is no positive result.
The exit is a fresh admitted command at its specified application slot or expiry
of the finite protection claim. Renewal requires a fresh check; merely remaining
inside the research geometry at sampled times does not renew it.

An exact simple success case is `x=vx=vy=0`, constant negative `y`, zero input and
zero disturbance: HCW leaves it stationary. A failure case has `y=-30.01 m` and
`vy=0.25 m/s`: zero command crosses the boundary before the first 200 ms decision
application. Other radial offsets or nonzero velocities can drift under zero thrust.
Fixtures and tests retain these contrary cases and response-loss intervals.

## Continuous inclusion argument

For arithmetic, scale position by 1 m, velocity by 1 m/s and time by 1 s. In these
dimensionless coordinates write `z'=A z+b`, where A is explicitly specified in
`iaa/enclosure.py` and b includes command effectiveness and disturbance intervals.
All interval bounds use exact rational arithmetic and outward quantisation to
multiples of 10^-12 in the scaled coordinates.

For a state box X and step h <= 0.05 s, let M bound the infinity norm of `A X+b`
and let L be the maximum absolute row sum of A. Set `r=h M/(1-h L)` and
`Y=X+[-r,r]^4`. Here h L < 1. The Lipschitz bound gives
`X+[0,h](A Y+b) subset Y`, and the corresponding integral map is a contraction.
Thus Y encloses the complete trajectories for every admitted initial state and
bounded input realization. The implementation then uses the more specific
`X+[0,h](A Y+b)` for a continuous tube and `X+h(A Y+b)` for the endpoint, rounding
both outwards. Repeated endpoint enclosures preserve containment by induction.
This is a conventional coarse Picard/Euler inclusion, not a new integration method.
The proof is mathematical reasoning checked with exact fixtures, not a proof-assistant
certificate or an independent physical validation. Array bounds may grow conservative.

The online checker propagates the uncertain initial box and declared actuation bounds.
The evaluator separately propagates a singleton initial state with the *actual fixture*
input/effectiveness schedule, without re-anchoring to numerical truth. It computes
continuous containment and sufficient dwell evidence. The same inclusion code is used
for both, so they are not independent implementations of the proof algorithm. Binary64
closed-form truth and independent matrix-series tests provide additional numerical
corroboration only. The evaluator records a numerical exit separately from loss of a
continuous containment proof. No safety probability or efficacy ranking is computed.

## Trust and maturity boundary

Versioned dataclasses reject mismatched units/frames, malformed times and nonfinite
inputs. The sink verifies request, command, information and validity bindings and
rejects late, duplicate or unsupported results. These are trusted in-process interfaces,
not a security boundary against malicious plugins or forged certificates. There is
no separate hardware watchdog or physical fault containment. No sensor calibration,
external navigation-engineer review, processor-in-the-loop run, hardware trial or
independent external replication has been performed for this phase.
