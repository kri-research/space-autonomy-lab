# Scientific question and analytical starting point

## Principal question

For a delayed, sample-and-hold spacecraft approach with bounded observation error and limited thrust, can a computationally bounded method return sound lower and upper bounds on the remaining observation-blackout duration compatible with a common recovery policy, while preserving more certified operating coverage or mission progress than matched robust output-feedback and delay-aware safety filters?

This is an untested algorithmic question for the nonconvex approach/hold constraint and explicit command queue. Generic uncertainty-aware protection, information-history propagation, recovery sets and blackout-duration safety already appear in prior work. Brunke et al. combine observer error bounds, predictive tubes and backup plans; Singletary et al. propagate stored commands through input delay; Mitsch and Platzer connect monitored assumptions and fallback to invariant preservation; Laine et al. compute safety kernels under lost observations. Their constructions must be treated as competing explanations/methods, not omitted to create novelty. No inspected source establishes that the proposed restricted computational tradeoff is solved or unsolved in general. Novelty remains a question until a concrete method and fair comparison are completed.

The specific target is a useful, sound gap between constructive recovery and proved common-policy impossibility under a declared per-decision computational budget. Repackaging an existing barrier value, adding age to a scalar threshold, or renaming an existing viability kernel would not satisfy that target. If a faithful existing method provides the same guarantee and tradeoff, the contribution should remain a rigorous spacecraft case study.

## Formal requirement and missing hypotheses

Let I_t contain the set of states compatible with the admitted observation history, deterministic uncertainty assumptions and known queued commands. Policies must be causal with respect to that same information pattern. Let K be a certified set of augmented information states with an admissible recovery policy preserving S; K is an unknown object to construct, not a label attached to all positions in S.

For an accepted candidate and the unavoidable queued inputs, a sufficient one-cycle obligation is: every compatible realization remains in S for the complete irrevocable interval, and every possible successor information state belongs to K. Every chosen fallback must satisfy the same obligation. If I_0 is certified, the uncertainty/dynamics/actuation and timing assumptions remain valid, numerical enclosures are sound, and this condition holds at every cycle, induction preserves S. This is a standard sufficient invariance argument, not a new theorem. It does not prove hold acquisition or other liveness goals.

The historical one-step screen establishes none of the complete set enclosure, uncertainty coverage, common-policy terminal recovery, or delay-history hypotheses needed for this implication. Its absence of a trip is therefore insufficient. Conversely, an unresolved numerical computation does not prove physical failure or the absence of a recovery policy.

The relevant quantifier is **there exists one information-compatible policy that works for every compatible state and disturbance**. The weaker statement **for each possible true state there exists a state-specific policy** permits privileged state knowledge and is insufficient. A computed empty necessary first-action set can prove absence of a common policy over that interval; it cannot establish that every actual state is individually unrecoverable.

For a fixed finite horizon and a specified terminal recovery obligation, define L* as the supremum of observation-blackout durations for which a common admissible policy exists. Any monotonicity claim requires nested information patterns: earlier observations can be ignored and no other constraints are changed. A constructive validated backup provides a lower bound L-, while a sound infeasibility argument provides an upper bound L+. The interval between them remains unresolved. No such spacecraft algorithm or theorem is claimed to have been produced in this task.

## Exact delayed-braking illustration

Consider a scalar clearance d>=0 and nonnegative closing speed v. At measurement time, d is at least d_lo and v at most v_hi. Braking cannot begin for L seconds, inward acceleration during that period is at most A>=0, and maximum braking guarantees net deceleration b>0. Assume the extrema are jointly attainable, including a worst-case realization whose best admissible braking achieves only b; a lower bound on braking alone would support sufficiency but not necessity. The exact worst-case stopping travel is

`D = v_hi L + A L^2/2 + (v_hi + A L)^2/(2b)`.

Integrating the delayed constant-acceleration phase gives speed `v_hi+A L` and travel `v_hi L+A L^2/2`. Integrating maximal braking adds `v_after^2/(2b)`. Since no admissible braking can arrest the worst case sooner, `d_lo>=D` is sufficient and necessary for robust arrest in this scalar model. Failure of this robust condition means an allowed realization cannot be saved, not that all actual realizations fail. This is known stopping-distance reasoning. It does not include orbital couplings, nonconvex obstacles or a spacecraft terminal safe set.

For this fixture only, L=age+delay because the uncertainty box is at measurement time and no tighter input-history enclosure is used. Starting from d=0.6 m, v=0.1 m/s and b=0.02 m/s^2, each of five changes alone remains arrestable: 0.1 m position uncertainty, 0.02 m/s velocity uncertainty, one second of age, one second of delay, or b=0.015 m/s^2. Together they require 0.72 m against 0.5 m lower clearance, giving exact margin -11/50 m. This illustrates composition of established effects; it is not a new universal failure law.

## Exact common-policy counterexample

For `qdot=v, vdot=u`, require `|q|<=1` and `|u|<=2/5`, with commands held for one second and no distinguishing observation during that second. The two possible initial states are `(9/10,1/5)` and `(-9/10,-1/5)`. Each is individually recoverable. For the right state, the consecutive one-second commands `-2/5`, `1/5`, then zero keep q in the interval and reach `(4/5,0)`; the left state uses the mirrored commands. Exact quadratic extrema verify the entire arcs, not only endpoints.

The right hypothesis requires `u<=-1/5` merely to make the first endpoint admissible; the left requires `u>=1/5`. Intersecting with the actuator range gives `[-2/5,-1/5]` and `[1/5,2/5]`, which are disjoint. No common first command, hence no common admissible policy under the stated information schedule, exists. The mean state `(0,0)` conceals this obstruction. These are exact constructed scalar trajectories, not recovered historical or new spacecraft episodes.

## Causal comparisons and refutation

The smallest causal experiment for the existing paper is a matched two-plant by two-predicate comparison: HCW versus nonlinear central gravity, and historical in-band versus closed-union online screening. Keep initial states, disturbances, sensing, controller, horizon, fallback and numerical screening method fixed. Use one independent offline physical property for all arms. Hold the numerical-screen implementation fixed across the predicate contrast or include it as a separate factor; do not conflate semantic and numerical changes.

With identical ideal primary and monitor estimates, the existing fallback can return exactly the original proposal. In that case changing the predicate can change rejection logs while leaving the applied commands identical. Record proposals, decisions, applied commands, continuous violations and timing separately. A lack of performance change in this ablation does not show that the corrected property is useless; it may show that rejection has no effective control consequence. Test effective fallback and intervention timing as distinct additional comparisons.

For the broader candidate, compare a faithful robust predictive output-feedback filter, a delay-aware sampled-data backup/barrier construction, and any new method under identical admitted observations, bounds, queued-input histories, thrust norms and compute budgets. An offline high-accuracy reachability calculation can adjudicate restricted examples but must not supply privileged online information. Separate within-assumption tests from stress cases that invalidate a baseline's assumptions. Report certification coverage, unsafe acceptance, unresolved rate, mission completion, intervention lead time, control effort and runtime; freeze primary claims and counts before final outcomes in Task 07.

One independently validated violation after a claimed within-assumption certification refutes soundness. A valid common recovery policy contradicting a claimed impossibility refutes that upper bound. Matching existing methods in guarantee and tradeoff defeats the proposed added-value claim. Failure on the preselected independent family limits transfer. Solver failure alone supports only unresolved status. All selected attempts, failures and competing explanations must remain visible.

## Held-out family and exposure rule

Select a nonorbital planar cart with first-order actuator lag: `pdot=v`, `vdot=a+w`, `tau_a adot=-a+eta u`, with delayed timestamped observations. It must use an independently written simulator and independently stated obstacle/target geometry. This is a simulation transfer family, not a physical robot. Its actuator state and lag distinguish it from changing only the orbital integrator.

Development may see these equations, units and interface requirements, but no family-specific trajectories, fitted parameters, outcome rates or policy tuning. Numerical parameter ranges, observation pattern, geometry and a disjoint seed namespace must be justified and frozen before transfer outcomes are exposed. No transfer trajectories or seeds are generated in Task 02. If later work inadvertently uses such outcomes for development, retain the disclosure and stop calling that set held out. Changing family requires a prospective reason unrelated to favorable results.

## Execution boundary

Task 02 implements property semantics and exact analytical fixtures only. Continuous-event adjudication belongs to Task 03; controller comparisons and final campaign execution belong to subsequent tasks. Physical validation requires actual equipment and measurements. Neither passing these tests nor a local timestamp constitutes a new safety theorem, independent human review, or external preregistration.
