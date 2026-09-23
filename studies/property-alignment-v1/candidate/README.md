# Common-command certificates under ambiguous observations

## Scientific scope

Task 05 showed that an existing predictive filter and a simple tracker resolve the selected earlier failures. This task therefore does not propose another controller as a breakthrough. It studies a narrower question: can a computational result distinguish a genuinely empty common-command set from failure of a sufficient safety search? The implemented output is a checked common safe prefix, a proved HCW first-command obstruction, or unresolved. A prefix is never labelled full recoverability.

The generic mechanism is established prior work. Partial-information viability, robust output-feedback tubes, interval sampled-data barriers and observational incompatibility already exist. The September 2026 preprint by Wan and colleagues explicitly treats incompatible safe decisions under observationally equivalent hypotheses. Our target is an executable, numerically checked specialization and concrete spacecraft counterexamples. Neither a new general impossibility theorem nor superiority to the intact Task 05 methods is asserted. `method_sources.json` specifies sources and reading limits.

## Information, dynamics and quantifiers

The state is (x,y,vx,vy) in the Task 02 target-centred planar frame, with SI units. The physical position set is exactly the original closed trapezoid/hold-ellipse union; the collision and keep-out components remain separate in adjudication. A declared information set is an exact finite union of initial boxes whose members are observationally indistinguishable during the next irrevocable control interval. The application interface permits zero/one second of observation age and zero/one second of input delay, and explicitly supplies every queued one-second command. It does not obtain hidden states or future observations.

The exact-information assumption is substantive. This code does not reconstruct that set from the historical Kalman filter, certify a sensor calibration, or infer a deterministic error bound from covariance. `outer_enclosure_only` can support sufficient prefix validation but cannot supply fictitious attainable witness points for impossibility. A common sensor bias can give the same packet under different hidden states even when the packet is authentic.

Control is a two-component acceleration with norm at most 1/50 m/s2, reduced further when specified. Effectiveness lies in a declared nonnegative interval, and each additive disturbance component has its own bound. For the positive interval-Taylor validation, effectiveness and disturbance may vary independently between explicitly split quarter-second segments and are constant within each segment. The negative calculation uses constant allowed realizations, a subset of that disturbance class. Arbitrarily fast unknown changes are outside this positive Taylor input model.

Let C_h(I) contain the constant commands which, after the known queue, keep every compatible realization inside S throughout the evaluated prefix. The quantifier is one command for all hypotheses. Checking a different action for each possible state is a weaker statement. Full recovery would additionally require a common continuation to a specified terminal obligation, or a sound invariant successor set with continued admissible observation-based control. We do not infer it from nonempty C_h. Conversely, an empty C_h rules out every policy that must begin with that one held command and receives no distinguishing observation before it ends.

## Exact scalar specialization

For qddot=eta*u+w, |q|<=L, |u|<=U, eta in[e0,e1] subset[0,1] and |w|<=W, an initial box has extremal trajectories q_hi+v_hi*t+(max(eta*u)+W)t^2/2 and q_lo+v_lo*t+(min(eta*u)-W)t^2/2. The positive convolution kernel establishes these bounds; constant extremal disturbances attain them under the independent-box assumptions.

Define B(c,v,T)=inf(0<t<=T)(2c/t^2-2v/t). If c<0, or c=0 and v>0, no finite acceleration is feasible. Otherwise B=-v^2/(2c) when c>0, v>0 and 2c<vT; in all other cases B=2c/T^2-2v/T. Differentiating gives stationary time 2c/v, and checking it and the endpoint proves the formula, including the closed-boundary cases.

Every eta*u must lie between W-B(L+q_lo,-v_lo,T) and B(L-q_hi,v_hi,T)-W. It is enough to impose these two bounds at both effectiveness endpoints, then intersect over the actual information boxes and[-U,U]. This proves necessity and sufficiency for one shared constant command over[0,T], not for arbitrarily switching policies. `scalar.py` evaluates the result in exact rational arithmetic. A separately implemented quadratic-extrema calculation tests it. The formula has acceleration units; time/length scaling is tested explicitly.

Known queue inputs are integrated first and checked continuously. Scalar upper position and upper velocity remain jointly attainable for the declared independent disturbances, so their propagated extremal pairs are sufficient here. This property must not be assumed for general vector outer enclosures. A bracket for the longest feasible single-held duration uses nested action sets; it is not a new characterization of arbitrary observation-blackout recovery.

## Sound necessary HCW obstruction

The linear HCW flow is affine in the initial state and each held input. `affine.py` encloses its maps by propagating six basis columns with the Task 03 interval Taylor implementation. For each truly compatible initial vertex and selected admissible disturbance/effectiveness realization, chosen-time membership in a halfspace containing all of S imposes M_i*u<=b_i. The six halfspaces are verified against every trapezoid vertex and the ellipse support function. They contain S but are not equivalent to it. At most 64 compatible vertices are used, which can weaken rejection power but cannot create a false impossibility claim.

A numerical linear program proposes nonnegative weights lambda. Its infeasible or failed status is never used as a proof. Instead, with outward intervals for M and b, compute exactly

`delta = -sum_i lambda_i*b_i_hi - U*sum_j max(abs(sum_i lambda_i*M_ij_lo), abs(sum_i lambda_i*M_ij_hi))`.

If delta>0, every input in the actuator disk, hence in its enclosing coordinate box, makes the weighted constraint violation positive. Indeed lambda^T(Mu-b) is at least delta, whereas satisfying all constraints would make it nonpositive. This is a complete residual-aware alternative argument. No exact numerical nullspace equality is assumed. Row residuals are nondimensionalized by 1 m or1 m/s2, and acceleration coordinates by 1 m/s2, before combining them. The returned dual margin is dimensionless.

The necessary rows propagate actual compatible origins through the known queue. They never treat corners of a propagated outer interval as reachable states. Omitting the exact-attainability requirement would invalidate the negative argument. The certificate stores its input identity, nonnegative rational weights and checked positive margin; it can be rechecked without trusting the optimizer. This negative result is implemented for HCW only. The nonlinear model is used for separate positive witnesses, without silently transferring the HCW impossibility proof.

## Constructive check and candidate search

An endpoint-constrained convex program suggests a command. The unaltered independent interval adjudicator must then verify the entire queue and held interval for every full hypothesis box, separately preserving the nonconvex union. A feasible relaxation does not certify safety. If the proposed command fails, the fixed small search also tries zero and the four axial extremes. A failed search, failed arithmetic or exhausted budget returns unresolved. A late computed answer is retained but supplies no applied command.

The terminal helper checks whether every final box lies in Task 05's represented quadratic terminal set. That label remains conditional on restoring the certified baseline's observation, timing and actuation assumptions. It does not synthesize a new recovery policy. The individual 300 s witnesses separately brake from a known state and use the existing bounded Hermite-reference tracker; they do not prove a common recovery policy for an ambiguous set.

## Development and comparison

`protocol.json` and source identities are sealed before the full development execution. Unit fixtures were already exercised; this is not external preregistration or protected evaluation. All 24 named contexts, 48 boundary-grid cases, 512 scalar cases with 17 commands each, and 10 individual recovery attempts are retained. There is no outcome-based replacement or tuning. The scalar comparison is exact and independently evaluated. The stopping-score shortcut is explicitly noncertifying and omits shared-action constraints; it is used only as an ablation.

The existing Task 05 predictive and barrier methods are unchanged. Both receive the same allowed data through an explicitly conservative hull adapter, with the previously selected settings and policy budgets. Their stronger recovery/continuation obligations and sufficient domains differ from a one-step prefix question. A prefix found when a baseline abstains is not a like-for-like superiority result. Reduced-effectiveness inputs outside their native assumptions are reported as unsupported, not as baseline failures. An unresolved independent recheck also must not be called a false baseline certificate.

The selected three-hypothesis example tests whether each pair has a common one-second action while the full set does not. All initial states, pair commands and individual braking commands were selected analytically. The intended negative proof does not imply that each actual state is unrecoverable. The paired full-set and hull examples examine unnecessary abstention from lost correlation. The outer-halfspace example tests why relaxation feasibility is insufficient. Age, delay, uncertainty and effectiveness ablations are specified separately.

## Reproduction and limitations

Use the existing `protective/requirements.txt` in an isolated environment, with SAL_EVIDENCE_ROOT pointing at the pinned historical checkout. From the study directory:

```sh
python -m pytest -c pyproject.toml --confcutdir=. candidate/tests
python -m candidate.develop --output /path/to/a/new/development-directory
python -m candidate.artifact /path/to/the/recorded-directory
```

The development directory must be new and outside both repositories. `recorded_development/` retains the completed execution. The artifact verifier checks all hashes, exact scalar decisions, replays the dual proof arithmetic and checks positive-result bindings. Full positive validity remains conditional on the tested interval implementation, the stated ODE and inputs. No hardware validation, learned-policy result, population prevalence, new general viability theorem or journal acceptance is claimed.

## Separate scalar recovery clarification

After the first development matrix, `refinement/` records an additional exact analytical check. For a symmetric pair at positions plus/minus b with outward speeds plus/minus v, deterministic authority U and full state revealed after blindness T, convexity and reflection of the scalar viability set make zero the optimal shared held action for feasibility. Recovery therefore requires b+v*T+v^2/(2U)<=L, whereas prefix containment only requires b+v*T<=L. The selected pair gives 1/4 s versus 1/2 s. Five exact two-path fixtures retain this distinction. These calculations do not change any original development output, and no general orbital recovery result is inferred.

## Post-execution fixed-input revalidation

The separate `verification/` module rechecks all 73 retained positive numerical certificates, including pair, nonlinear and baseline-action checks, and all ten 300 s individual recovery schedules. It regenerates neither controller decisions nor random trials and leaves the original budget miss and other outcomes unchanged. The recorded revalidation passed under the same model and interval-arithmetic assumptions. Reproduce it with `python -m candidate.verification.replay candidate/recorded_development --output /path/to/a/new/revalidation-directory`. This is numerical revalidation, not independent human or physical review.
