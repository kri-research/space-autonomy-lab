# Protective baseline implementation

This additive subproject implements two existing protective-control constructions for the declared spacecraft benchmark. It does not claim a new safety filter or replicate the original authors' published numerical experiments. Historical results, the Task 03 numerical artifact and the Task 04 developmental experiment remain unchanged.

## Method and assumption matrix

| Item | Tube predictive filter | Sampled high-order barrier filter |
| --- | --- | --- |
| Published construction | Wabersich and Zeilinger, nominal/robust predictive safety filter, equations 5 and 6 and stored shrinking-horizon backup; Brunke et al., estimation-error tubes and terminal protection, equation 18 | Xiao and Belta, high-order barrier recursion and initial derivative-domain requirements; Singletary et al., sampled-data uncertainty and known-command delay propagation |
| Reconstruction | Linear deterministic tube specialization, fixed stabilizing feedback, safe terminal ellipsoid and finite schedule enumeration | Relative-degree-two constraints on each smooth component, evaluated conservatively over the entire held-command interval |
| Information | Full-state bounded packet, known error components, up to one-second data age and one-second command delay | Exactly the same observation and queue adapter |
| Nonconvex set | Enumerates four corridor-to-ellipse switch times; switch state belongs to both sets; each interval belongs to one convex component | Accepts either smooth component only when its position and first-derivative barrier conditions hold |
| Declared conservatism | Does not search all possible component-switch sequences; additional 2 m/s numerical-domain cap; no claim of full viability coverage | Sufficient derivative domain can exclude recoverable states; no claim that failure proves physical impossibility |
| Failure | Keeps the last feasible tube plan and terminal feedback while its assumptions remain valid; otherwise returns no protected action | Returns no protected action when neither component is certified; a one-step barrier result does not prove future optimization feasibility |
| Independent checks | Solver primal/dual residuals, explicit nominal trajectory reconstruction, tightened constraints, interval-verified Lyapunov/support inequalities | Solver primal/dual residuals plus direct interval reevaluation of the selected input's second-order barrier inequality |
| External continuation | Both methods explicitly record the same bounded reference tracker when no certified action is returned. Its use is not counted as filter success. | Same |

The original authors' MIT-licensed MATLAB/CasADi/YALMIP implementation was inspected at the commit recorded in `method_sources.json`. Its mass-spring-damper dynamics, partial-observation MHE, solver infrastructure and tuning are not represented as executed here. The full-state bounded observer used here is an explicit specialization that avoids claiming the original nonlinear observer theorem without its hypotheses. These are transparent research implementations of published constructions, not untouched distributions from those authors.

## Predictive construction

Write z for nominal state relative to the hold equilibrium, e for actual-minus-nominal state and eta for estimate-minus-actual error. A stored plan applies u_i + K(estimate - z_i - target). Thus e_next = (A+BK)e + BK eta + d. An interval-checked matrix inequality establishes ||A+BK||_P <= gamma = 0.98. All observation-age and command-delay errors are propagated through their known inputs. A positive comparison-system exponential bounds arbitrary bounded additive disturbance, rather than incorrectly interpreting abs(exp(A)) as such a bound. The additive radius recurrence is r_next = gamma*r + delta. Its corner/support constants and numerical-map reserve are recorded by `certificates.py`.

Nominal node constraints are tightened by the propagated P-norm radius, the feedback input reserve and a 0.006 m continuous-arc allowance. Both endpoints of an interval use the same convex component. With ||u||<=0.02, ||v||<=3 and position radius below 150 m, an acceleration bound below0.035 m/s2 gives deviation from the endpoint chord below0.035/8 m over 1 s. The 0.006 m allowance exceeds this and the ellipse's corresponding scaled allowance is0.003. The speed domain is bootstrapped from node speed<=2 and the same one-second acceleration bound; it does not assert an operational approach speed limit.

The terminal ellipsoid ||state-target||_P<=0.075 is inside the hold ellipse and satisfies a continuous speed bound below 0.05 m/s. The checks establish gamma*alpha+delta<alpha, input authority and continuous motion margins for the declared uncertainty. A failed new optimization can therefore use the remaining admitted feedback tube and then terminal feedback. This conditional mathematical argument requires the initial uncertainty, model and actuation bounds to be true. Finite tests and a floating-point solver are not a machine-checked implementation theorem.

The nonlinear circular-chief model is covered as an additive HCW discrepancy only inside the stated150 m local domain. A bound 24*mu/r_min^4 on the central-gravity Hessian norm yields remainder<=12*mu*||rho||^2/r_min^4, below the declared 1e-7 m/s2 component allowance. It excludes eccentric chief motion, attitude effects and additional unmodeled forces. The end-to-end numerical experiment is still evaluated as a fixed recorded input schedule by the separate interval ODE implementation; approximate feedback generation is not claimed exactly equivalent to a mathematical feedback law.

## Barrier construction

For each smooth h>=0, define psi1=hdot+k1*h. The input occurs in the second derivative. A held input must satisfy hddot+(k1+k2)*hdot+k1*k2*h>=0 throughout the command interval, starting with both h>=0 and psi1>=0. The code encloses every admissible state over that interval with interval nominal propagation and a comparison-system uncertainty bound, then solves conservative affine/absolute-value input constraints. For the ellipse it includes the velocity-quadratic Hessian term. It does not differentiate a minimum over components.

A selected smooth component is preserved for one command interval by the comparison principle. At the next decision either the same component or another independently admissible component is required. The implementation makes no assertion that this search remains feasible for every state in S. When it stops certifying, the record explicitly identifies the external continuation. The method's theorem is not blamed for violating its entry or persistence hypotheses.

## Development and reproducibility

`protocol.json` defines all cases and the complete bounded tuning budget before closed-loop baseline outcomes. Each family receives two 300 s HCW midpoint tuning runs; every attempt is retained. The fixed ranking is containment, uninterrupted filter certification, hold acquisition and then lower applied control effort. The selected settings are used for all 72 subsequent comparison cells. These are development data, not the future frozen evaluation or the preselected transfer family.

The unprotected, original gate, property-aligned one-step and bounded tracking controls share the same new observation adapter, thrust, command rate and queued inputs. They retain their own disclosed protection semantics. The old gate's source is unchanged, but its input adapter is different from the historical Kalman filter; no rerun of the historical campaign or Task04 is claimed. Uniform bounded observation levels and disturbances are research choices. A covariance matrix alone is never promoted to a deterministic bound.

Use a separate environment from historical reconstruction:

```sh
python -m pip install -r protective/requirements.txt
export SAL_EVIDENCE_ROOT=/path/to/pinned/evidence
export OPENBLAS_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
python -m pytest protective/tests
python -m protective.binding
python -m protective.run tune --output /path/to/new-tuning-directory
python -m protective.run compare --selection /path/to/new-tuning-directory/selection.json --output /path/to/new-comparison-directory
```

The two execution directories must be new and outside both repositories. No automatic retry overwrites a selected attempt. The application time is distinct from wall-clock time. Per-subproblem limits are 0.2 s, the whole-decision policy budget is 1 s and cone compilation is separately measured initialization. A measured run meeting that budget is not a worst-case execution-time proof. A late or failed optimization is rejected; any available stored-plan fallback is recorded.

The initial diagnostic serializer failure and all four partial tuning attempts are retained in `retained_attempts/serialization-v1/`. The explicit serialization-only amendment preserves the original cases, controller equations, endpoint definitions and ranking. The valid amended tuning selection is kept separately. Policy-call timings exclude shared observation/proposal preparation, external continuation and offline event adjudication; they are not end-to-end processor deadlines.
