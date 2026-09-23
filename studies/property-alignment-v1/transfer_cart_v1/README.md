# Shared-command transfer to a lagged cart

This study uses the nonorbital cart family selected before the spacecraft campaign
in `specification/research_question.md`. Only its equations and interface had been
exposed. Numerical settings, geometry and the 128-case design were specified in
Task09 after the spacecraft evaluation, then locked before the new outcomes.
This is a prospective simulation transfer, not a physical robot or independent team.

## Physical model and information

The state is (px,py,vx,vy,ax,ay), with pdot=v, vdot=a+w and
adot=(-a+eta*u)/tau. Acceleration is commanded within a Euclidean disk of
radius0.4 m/s2, derived from the declared synthetic2 kg cart and0.8 N force limit.
The lag, effectiveness, full six-dimensional measurement boxes, zero queued inputs,
constant bounded disturbances and triangular center-position constraints are in
`design.json`. These are research parameters, not measurements of equipment.
A timestamped packet identifies a union of boxes and gives no privileged true-box
index to any controller. The held interval is one second after the known queue.

For a constant projected input c=eta*n.u, the position response after application is
G(t)c, where G(t)=t^2/2-tau*t+tau^2*(1-exp(-t/tau)). The initial acceleration
coefficient is F(t)=tau*t-tau^2*(1-exp(-t/tau)). The closed triangular region has
unit rational face normals (1,0),(-3/5,4/5),(-3/5,-4/5), all with bound1 m.
Initial position, velocity and acceleration kernels are nonnegative, so each
face maximum over a box and constant disturbance is attained at a compatible
corner. This is used as a necessary obligation, never as a replacement of the
complete information set by its mean.

## Criterion and comparison obligations

The lag-aware criterion first checks a nonnegative dual combination of necessary
halfspace constraints. A positive residual-aware rational margin proves no common
held command; a failed optimization proves nothing. Otherwise, a minimum-norm
proposal is admitted only after continuous-prefix checking. On each subinterval,
an upper acceleration bound times dt^2/8 bounds deviation from the endpoint chord.
Directed decimal enclosures include the endpoint-map error.

The robust predictive comparator is re-derived as a one-hold prefix-feasibility
specialization with64 subdivisions. It has the same finite-prefix obligation as
the diagnostic. It is NOT a port of the original spacecraft terminal-set/full
recovery theorem. No general benefit over established predictive filtering is
claimed. The exponential barrier uses relative degree THREE: psi1=hdot+lambda*h,
psi2=hddot+2lambda*hdot+lambda^2*h, and
psi3=h_third+3lambda*hddot+3lambda^2*hdot+lambda^3*h. Initial h,psi1,psi2
must be nonnegative, and the held input satisfies psi3>=0 throughout the interval
using derivative bounds. lambda=2/T is fixed before evaluation. Future recursive
feasibility is not asserted. Mean-only and instantaneous-actuator constructions
are explicitly incomplete diagnostic ablations, not credited as sound baselines.

## Independent event referee

`reference.py` imports neither the online formulas nor orbital code, optimizers,
NumPy or SciPy. It integrates each supporting projected trajectory with an
80-digit outward Taylor expansion and Bernstein convex-hull bounds. The step is
at most tau/2. A degree10 exponential-series tail bounds truncation at every point
of the step. Endpoint witnesses can refute containment; only continuous range
bounds can establish it. Unknowns stay unknown. The independent negative recheck
builds its response coefficients by Taylor integration, not the online exponentials.
Shared items are the declared physical model, geometry and input schema. This is
independence of computational formulation, not independent authorship or laboratory
replication.

## Evaluation and limits

All128 planned inputs remain in four separately reported groups. The five methods,
proper singleton/pair subsets, one-second policy budget and reference rules are
fixed. Sixteen predeclared mismatched-lag checks use unchanged commands but a lag
four times the declared value; those are outside-assumption stress tests and are
reported separately. Closed-loop recovery, hold acquisition and mission utility
are not evaluated. A finite prefix cannot be renamed a recovered spacecraft.

Run tests from the parent study directory with the pinned isolated environment:

```sh
python -m pytest transfer_cart_v1/tests
```

The calibration and protected commands require fresh private output directories.
The protected execution requires the frozen identity and explicit authorization.
Raw attempts are write-once, watchdog failures remain visible, and reporting never
reruns a policy. `cleanroom.py` rechecks recorded commands and dual evidence from
an isolated standard-library-only source export and fresh virtual environment;
its execution is numerical reproduction, not a new test population or timing trial.
