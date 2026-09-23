# Independent event adjudication

This additive module evaluates the Task 02 physical contract without importing the online gate or historical geometry. It preserves all historical implementations and records. Its evidence is bounded numerical validation, not a new comparative campaign or physical measurement.

## Supported problem

The flow encloses planar HCW or circular-chief nonlinear relative dynamics under explicitly supplied, piecewise-constant local acceleration. All command, disturbance, observation and fault change times must be supplied as exact segment boundaries or required events. Intervals can represent a constant unknown input on a segment; arbitrary time-varying disturbances, eccentric chief motion, nonplanar motion and unmodeled effects are unsupported. The caller must provide the realized input schedule rather than silently substitute zero thrust.

The nonlinear equations are independently implemented in rotating relative coordinates. The mathematical constants denote their represented values. Nonlinear mean motion is enclosed from sqrt(mu/R^3); HCW mean motion uses the historical represented constant. Numeric coordinates correspond to position scaled by 1 m, velocity by 1 m/s and time by 1 s. Picard norm and contraction calculations use these scaled coordinates.

## Continuous enclosure

For initial box B0, held input U and step h <= 0.25 s, the code finds an a priori box Y satisfying

```
B0 + [0,h] F(Y,U) subset Y
h * L_infinity(Y) < 1
```

Here F encloses the smooth vector field and L is an analytic Jacobian row-sum bound. Gravity-domain positivity is checked. The closed Picard inclusion and contraction support existence and uniqueness for every admitted initial value and constant input. Failed inclusion, singularity, overflow or unsupported arithmetic raises an error.

The default order-eight Taylor construction keeps coefficients zero through seven at B0 and bounds coefficient eight throughout Y. Interval automatic differentiation includes factorial scaling. For each component and 0 <= tau <= h,

```
x(t0+tau) in sum(k=0..7, c_k(B0,U) tau^k) + c_8(Y,U) tau^8.
```

The same polynomial/remainder encloses intermediate times. Endpoint enclosures, rather than a fresh nominal state, initialize subsequent steps. This is a conventional interval Taylor construction; it does not claim a new integration theorem or reproduce the parameter-dependency algorithm of Lin and Stadtherr.

## Arithmetic and classification

`interval.py` widens each nontrivial binary64 basic operation outward by one representable number, under the stated IEEE-754 rounding assumption. Square-root endpoints are checked against exact rational squares. Overflow is rejected. `polynomial.py` supplies a structurally different exact-rational Bernstein range enclosure for analytical fixtures, not a spacecraft propagator. Tests compare the arithmetic against exact rational answers, including subnormal inputs.

`geometry.py` evaluates four corridor halfspaces, the ellipse, squared separation and squared speed with rational arithmetic on box endpoints. Containment requires the whole enclosure to satisfy either component; it never replaces the union by an intersection. Failure to resolve an overlapping box triggers subdivision or an unresolved result. An exclusion witness requires an enclosed point outside both components. Closed collision and keep-out contact counts as a violation; contact with the permitted closed union is allowed.

There is no copied 1e-9 m tolerance in new sign decisions. Each residual interval directly incorporates component uncertainty: corridor residuals have units m, ellipse residual is dimensionless, squared separation has units m^2 and squared speed has units m^2/s^2. An uncertainty box crossing a boundary is unresolved. For the sufficient separation witness, the entire enclosed radius must be below 27 m. With the historical excess allowance epsilon, the lower bound becomes 27 - 1.5 epsilon for the specified small positive epsilon. This tolerance adjustment does not estimate integration error.

## Temporal evidence

`engine.py` validates complete ordered coverage, equal propagated boundary boxes and all required split times. It bisects continuous range enclosures when any component or hold eligibility is undecided. A proven-inside prefix and an enclosed outside point bracket the first exit; root finding or point sampling alone is never used to exclude earlier excursions. The reported bracket encloses the exit infimum, not an exact time.

The result distinguishes `validated_containment`, `validated_violation` and `unresolved`. The separate `numerically_corroborated_violation` helper compares numerical representations without claiming that their spread bounds truth error. It never certifies containment. Validation labels concern the stated mathematical ODE or polynomial, inputs and arithmetic assumptions; they are not physical validation, machine-checked proofs or operational safety claims.

Hold evaluation accumulates a lower dwell bound from intervals entirely eligible and an upper bound treating unresolved intervals as possibly eligible. Only an interval proved nowhere eligible resets the upper-bound run. An existential violation survives later holding or abort. Missing intervals, nonfinite values, failures and exhausted budgets cannot become safe outcomes. A failure in any range calculation suppresses the whole-episode minimum-separation enclosure even when an earlier valid violation witness remains.

`adjudicate_execution` wraps propagation and adjudication failures as unresolved. The lower-level arc API accepts only the implemented enclosure types and is an internal trusted interface, not an authenticated verifier for arbitrary externally supplied certificates. Later statistical analyses must retain unresolved counts and must not score them as successes.

## Preserved numerical defect

`extrema.py` versions the supplied sample-preserving helper as `sample-preserving/1.1`. It retains all sampled candidates, validates optimizer output and refined reevaluation, exposes exceptions, nonfinite/out-of-bracket values and inferior refinements, and raises in strict mode. The original 65-node helpers are exercised separately. Their failure is demonstrated in controlled software fixtures, not attributed to a historical episode. The narrow-between-node counterexample remains a miss for both grid/refinement helpers; sample preservation is not an exhaustive search guarantee.

## Validation and reproduction

`validation_protocol.json` declares the fixtures and resolution checks. `input_commands.json` preserves all 300 nonlinear-plant commands from the previously declared midpoint diagnostic, with original input identities. Their outcomes were already known. Replaying this fixed sequence through both models isolates numerical propagation; it does not regenerate controller feedback or become a new confirmatory trial.

Run from `studies/property-alignment-v1` with the study's pinned Python environment and a separate clean evidence checkout:

```sh
export SAL_EVIDENCE_ROOT=/path/to/pinned/space-autonomy-lab
export OPENBLAS_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
python -m pytest tests/test_adjudication.py tests/test_adjudication_numerics.py
python -m adjudication.validate --output /path/to/new-validation-directory
```

The output directory must be new and outside both repositories. The driver records eight exact curve fixtures, twenty original-helper failure fixtures, analytic frame checks, independent relative and original inertial comparisons, and four interval-flow continuations. Integration step and event subdivision are varied separately. `recorded_validation/` retains one completed execution and a file manifest. Tests retain known answers in executable assertions and disclose their separate observation scope.

At event subdivision 1/4096 s, both supported models bracket the first exit of the fixed-command continuation between 98.010986328125 and 98.01123046875 s. Remaining ambiguous boundary intervals are recorded; the overall violation is established by an enclosed outside witness and the lower time limit by a proven-inside prefix. The narrower step does not monotonically decrease interval widths or inertial-reference differences. These observations do not establish a convergence order or add a physical-error bound.

## Method sources

Y. Lin and M. A. Stadtherr, *Validated solutions of initial value problems for parametric ODEs*, Applied Numerical Mathematics 57(10), 1145–1162 (2007), DOI 10.1016/j.apnum.2006.10.006. The traditional interval Taylor background, a priori inclusion and remainder construction in Sections 4.1–4.2 support the method description. Their specialized parameter-dependency algorithm is not implemented here.

The SciPy 1.17.0 `solve_ivp` documentation distinguishes estimated local errors and sign-change event detection from exhaustive continuous-time event coverage. The DOP853 traces here supply a numerical comparison only. Source URLs, versions and access scope are recorded in `method_sources.json`; no third-party article or implementation is redistributed.
