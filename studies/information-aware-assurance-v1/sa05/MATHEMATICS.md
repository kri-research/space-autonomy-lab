# SA05 finite-manoeuvre comparison

## Claim and experimental unit

The question concerns a single 4.2-second inspection manoeuvre under a finite
preloaded protection contract. It asks whether decision-aware sensing improves
new acquisition of the existing two-second goal dwell, and what sensing and
computational costs accompany it. It does not test a complete inspection mission,
long-term recovery, recursive feasibility or an operational spacecraft.

An experimental unit is one sampled initial state with its exogenous latent
conditions. Four methods share that unit, its supplied initial box, permitted
sensors, command menu, actuator limits, noise variables and modeled budgets.
Packets, integrator steps and measured timings are not independent trials.

The existing fixed-range, fixed-bearing, uncertainty-triggered and decision-aware
policies are unchanged. They use the same SA03 finite action menu and supported
common-action checks. The SA05 adapter exposes all four through the same SA04
observation reconstruction and realized-action checker. Fixed schedules always
request their chosen channel if their complete protected plan is available;
they cannot request a fictitiously guaranteed reading after a failed plan.
No baseline is weakened to make the candidate win. No policy parameter is tuned.

## Nonlinear evaluation dynamics

Basilisk 2.12.0 integrates a unit-mass deputy under central point-mass gravity.
The analytical circular chief has mean motion n=0.0011 rad/s and radius
R=(mu/n^2)^(1/3), where mu=398600441800000 m^3/s^2 is a declared model constant.
For radial/along-track displacement p, the inertial deputy position is
r_c+C(t)p and its velocity is v_c+C(t)(v+Omega cross p). The inverse conversion
subtracts the same rotating-frame velocity term. This avoids treating inertial
relative velocity as the derivative of the rotating coordinates.

The internal integration interval is 1 ms. The commanded inertial force is held
for at most 5 ms using the analytical frame at the interval midpoint. Segment
boundaries include every observation epoch, command start and command end. The
unit mass makes numerical force in newtons equal numerical acceleration in
m/s^2. No attitude, propellant consumption, ephemeris, J2 or physical hardware is
represented. These deliberate omissions limit the scope, rather than supplying
unmodeled realism to the assurance claim.

A separate nonlinear relative-coordinate ODE is integrated with DOP853. A second
linear reference uses a matrix exponential independently of KRI's interval
propagator. Reference tests compare units, frames, force direction, switching,
interpolation and endpoint states. This is independent numerical machinery on
the same host, not an external laboratory replication.

## Relating nonlinear dynamics to the HCW assurance model

For gravitational acceleration g(r)=-mu r/||r||^3 and ||p||<=rho<R, a conservative
operator norm bound on its second derivative is 24 mu/(R-rho)^4. Taylor's integral
remainder therefore bounds the nonlinear residual by

    ||g(r_c+p)-g(r_c)-Dg(r_c)p|| <= 12 mu rho^2/(R-rho)^4.

This bound follows by differentiating g twice, using absolute norms on all terms;
it deliberately exceeds the tighter attainable directional constant. Centrifugal
and Coriolis contributions are linear for the circular chief. Holding a rotated
force for h seconds adds at most n h ||a|| to the acceleration discrepancy.
With rho=100 m, h<=0.005 s and ||a||<=0.020003 m/s^2, their sum is below 1.4e-7
m/s^2. Adding the explicitly injected component disturbance of at most 2e-6 is
below the existing per-component 1e-5 m/s^2 allowance. Effectiveness remains in
[0.8,1] for the within-assumption strata. Thus the nonlinear force model lies in
the declared differential-inclusion envelope over this domain.

That argument does not validate floating-point integration. The evaluation uses
explicit engineering allowances of 1e-5 m position and 1e-7 m/s velocity, tested
against separately implemented nonlinear integration on declared development
fixtures. They are not machine-verified universal error bounds. All trajectory
adjudication is labeled numerical; no physical safety probability is inferred.

## Continuous numerical event adjudication

The stored trajectory has samples at most 5 ms apart. In the tested domain,
component acceleration magnitude is conservatively bounded by 0.1 m/s^2. Between
endpoints separated by h, departure from the position chord is at most Ah^2/8.
A velocity interpolation enclosure expands by Ah/2. Numerical allowances are
added before assessing the research box, the 10 m exclusion circle and goal
eligibility. A sample beyond a constraint by more than its allowance establishes
a numerical violation. Failure to prove either containment or violation is
reported as ambiguous, never silently counted as safe.

The goal requires x in [-0.35,0.35] m, y in [-40.35,-39.65] m and speed <=0.05 m/s
continuously for two seconds. New acquisition requires the initial state to be
outside goal eligibility. Already-eligible successes are reported separately.
A 500 ms task-potential decrease is secondary and does not establish this dwell.

## Information, timing and resources

All methods receive only delivered observations. Sensor values are regenerated
from each method's own plant state and the preassigned latent noise for that
channel/epoch. Copying measurement values between different geometries is forbidden.
The simulated episode has one optional range or bearing request at 250 ms, a
650 ms checking snapshot, a [700,710] ms initiation window, a fixed 1200 ms
command end and protection expiry at 4200 ms. Late planner/checker replies and
missed initiation windows remain uncredited for a new command. Only the separately
checked initial coast can retain conditional protection when a candidate is absent.

Actual host computations run offline. Their duration, CPU use and memory high-water
marks are retained separately. Frozen simulated completion times do not assert
that the measured implementation meets those times. Previous SA04 cold-path
failures remain valid evidence. Physical communication, sensor, actuator and clock
alignment delays remain unmeasured.

SA05 uses an explicit additive accounting model: 5 mJ initial decision, 5 mJ
realized checking, 0.001 mJ per counted planning, observation-construction and
checking operation, and 0.2/0.3 mJ per requested range/bearing acquisition, including
the common initial measurement when present. Failed work is charged. The input
and work caps imply less than 262 mJ even at their configured maxima, below the
same 500 mJ allowance for every method. This is a resource model, not a conversion
from CPU duration to actual energy. Offline prearming, propulsion, base avionics
and physical power are excluded. All exclusions are explicit in the results.

## Prospective design and analysis

Development units and their exposure record precede final sample-size selection.
The held-out master seed and latent inputs are generated once after that decision.
The complete source, dependency versions, input file and analysis are deposited
on public GitHub before running any held-out outcomes. This is a timestamped
source deposit, not externally administered preregistration. The generator uses
separate cryptographic-hash streams with rejection sampling on declared discrete
grids. Statistical interpretation assumes their usual pseudorandom independent-
unit approximation and concerns this artificial scenario distribution only.

The two in-model strata have four primary comparisons in total: decision-aware
minus fixed range and minus uncertainty-triggered for new goal acquisition.
Exact conditional tests use the discordant pairs under equal marginal success
probability; Holm controls the four-test family. Conservative simultaneous
intervals use signed paired outcomes in [-1,1] and Hoeffding's inequality, with
per-comparison alpha=0.0125. These intervals can be wide. Marginal exact binomial
intervals are supplementary and not simultaneous. Outside-assumption strata are
descriptive only. No equality or noninferiority conclusion follows from a null test.

Each scheduled cell is retained even on infrastructure failure, timeout or global
budget exhaustion. Such missing outcomes are not safety events. Missing pairs
suppress the primary test and produce explicit worst/best identification intervals.
No method, sample, analysis or outcome definition is changed after the freeze.
Any substantive defect discovered later requires preservation and a new identity.

Unnecessary abstention is left unestablished where no independent feasible-policy
oracle exists. The metric is present with an explicit null value. Observed unsafe
admission, unresolved decisions, missing inputs, latency failures, finite protective
continuations and out-of-model state exclusions are reported separately.
