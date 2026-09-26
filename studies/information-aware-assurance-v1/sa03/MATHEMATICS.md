# SA03 sensing before a scheduled control opportunity

## Scope and inherited model

This is an additive, simulation-only enhancement of KRI Space Autonomy. The SA01
HCW equations, SI frame, standoff box, actuator norm 0.02 m/s2, effectiveness
[0.8,1], component disturbances 1e-5 m/s2, 500 ms held action, goal geometry and
three-second coast are unchanged. SA02 supplies bounded observation-conditioned
outer cells and constant latent bias hypotheses. Existing sources and results
are imported unchanged at the identities in source-map.json.

The new development experiment is deliberately one sensing opportunity and one
subsequent held action, rather than the earlier 30-second feedback experiment.
It does not establish repeated recursive feasibility, fault identification,
full spacecraft recovery, optimal sensing, real-time feasibility or novelty of
active sensing. E001-E005 and previous campaigns are not rerun.

## Actual simulated application times

The decision snapshot is d=100 ms. The previous known command lasts until 200 ms;
the chosen waiting command is zero from 200 to 700 ms. A modeled 50 ms planner
finishes at 150 ms, requests a chosen channel, and the unchanged 100 ms request
lead puts acquisition at 250 ms. Default range/bearing availability is 290/320 ms.
A further modeled 50 ms of processing/checking is included before the fixed
700 ms application slot. The action lasts until 1200 ms, followed by zero-command
coasting through 4200 ms. Every method has the same slots and obligation.
Acquisition uncertainty is +/-2 ms. The estimator's initial observation history
ends at d; it receives no future values or evaluation truth.

These are clock assumptions for offline functional development. The implementation
records actual planner and complete selected-tree rechecking times separately.
An observed host overrun is not silently moved to a later proved application time.
A missing, delayed or invalid reading invokes the explicitly checked no-observation
branch. Late dispatch cannot start a newly shifted command. No protection is claimed
past 4200 ms. The tree's protection starts at the supplied decision set at 100 ms;
its initialisation before that time needs the prior-stage contract.

## Quantifiers and complete outcome cover

Let I_d be the supplied SA02 outer union, including state and persistent bias.
For a sensing option s, the fixed known/waiting input defines a reachable outer
union at q, the latest possible acquisition time. The same rational propagation
bounds all permitted effectiveness and disturbance histories. A bound V_j on
velocity over the acquisition interval [l,q] yields

    |p_j(q)-p_j(tau)| <= V_j (q-l)/1000,  tau in [l,q].

The reading contractor uses that inflation and the SA02 sensor error/fault model.
It adapts the necessary polar constraints to a whole reading interval J, including
sensor error, instead of substituting an interval midpoint as a future reading.
Fault-window boundary modes are both retained; loss of correlation enlarges the
representation. Constant latent offsets are not independently redrawn per branch.

For range, the union of predicted radius plus common/channel offsets and error
gives a complete outer reading interval. For bearing, [-22/7,22/7] contains every
wrapped reading. Recursive closed bisection covers the entire initial interval;
adjacent leaves share endpoints. A leaf can be excluded only when all corresponding
cells fail a necessary measurement constraint. Otherwise its retained outer cells
are propagated to the actual 700 ms application time using the known queue.

A returned checked tree establishes, conditionally on the stated models:

    every possible timely valid reading lies in a retained partition leaf;
    every retained leaf has one common action for all its represented states;
    every such action preserves the constraint for its hold and subsequent coast;
    the known queue and waiting interval also preserve the constraint;
    a separately checked no-observation action covers missing/invalid/late packets.

Thus reading-dependent action selection covers all admitted outcomes, including
absence of a reading, through the same finite endpoint. One unsupported leaf
prevents a universal positive tree. Failure of the finite search is unresolved;
no outer-box corner is exported as an attainable impossibility witness.

This is a conservative constructive composition of existing inclusion and
set-membership methods. It is not a characterization of all feasible policies.
The implementation checks five commands: zero and four axial accelerations at
the existing authority. Other commands or waiting manoeuvres may work when this
search returns unresolved. Complete trees are independently recomputed by the
local verifier before simulated dispatch; hash equality alone does not certify them.
This uses related numerical machinery, not an external replication.

## A precise limited definition of usefulness

The task potential is V(p)=x^2+(y+40)^2, in square metres. For a candidate's first
500 ms, rational velocity tubes give a displacement enclosure D containing the
integral of velocity. With initial position error E, the true change satisfies

    V(p_end)-V(p_start) in sum_j (2 E_j D_j + D_j^2).

Dependency loss in these interval operations can only weaken this bound. An action
is called useful if the upper bound is at most -1e-6 m2, or every tube during that
hold is inside the existing goal-position and speed eligibility conditions.
The latter is only 500 ms of eligibility, not the required two-second mission dwell.
A decrease for one step is not convergence, fuel efficiency or mission completion.
Those outcomes are recorded separately rather than inferred from this label.

The decision-aware rule first checks whether an existing no-observation action is
already useful. Otherwise it considers range and bearing and requests the cheaper
channel only if every retained reading leaf supports a useful action. Utility is
conditional on a timely in-model reading. The missing-reading branch must be
protected but need not be useful. No universal mission-success claim is returned.
If neither channel passes, the checked no-observation action remains the simpler
alternative. Hypothesis count and entropy are not utility certificates.

Reading resolutions (1/8 m and 1/128 rad), depth 12, the five-command list, the
cost-based tie break and uncertainty-trigger threshold are declared engineering
choices. They are neither learned sensor tolerances nor optimality claims.

## Exact scalar refutations and timing condition

For qddot=u, |q|<=L and |u|<=U, consider exactly known alternative states
(q,v)=(b,v) or (-b,-v), b>=0, v>0, with no disturbance. Their sign is unknown.
A command held without distinguishing information through H must satisfy both
endpoint inequalities. Adding them gives b+v H<=L. Zero meets this condition
at all intermediate times, so b+v H>L is a genuine obstruction for this particular
shared constant-command class. It is not a spacecraft impossibility result.

Suppose zero is held until T, a sign-distinguishing measurement has arrived and
been checked, and maximum opposite acceleration is then applied for v/U seconds.
The maximum outward position is b+v T+v^2/(2U). The exact latest braking application
for this policy is

    T_max = (L-b-v^2/(2U))/v.

If acquisition is at a and the acquisition-to-application delay is ell, require
(a+ell)<=T_max. A bounded scalar position error e distinguishes every possible
reading exactly when e < b+v a; equality permits an overlapping zero reading.
This condition concerns the observed state at acquisition and the controlled state
at application separately. With b=0.7 m, v=0.2 m/s, U=0.4 m/s2, L=1 m and ell=0.25 s,
T_max=1.25 s and the latest acquisition is 1 s. The disturbance-free stopped state
can coast forever only in this scalar specialization. That conclusion is not
transferred to HCW or the uncertain actuator model.

Examples retain timely rescue, the exact boundary, a late but still contained wait,
an unsafe wait, overlapping readings, information that removes only an irrelevant
label, and an already adequate action. Additional information does not universally
repair missing control authority or incompatible required actions.

## Resources and comparison boundaries

All four schedules use the same initial information, five-command search, physical
obligation, resource cap and sensor options. Fixed-range and fixed-bearing schedules
always request their named channel when the complete protected tree is available.
The uncertainty comparator requests a channel only when a position width exceeds
0.25 m, choosing bearing for larger radial width and range otherwise. This geometric
rule is a heuristic, not an information-optimal or published baseline reconstruction.
The decision-aware rule uses the all-reading usefulness criterion above.

The resource model charges 5 mJ per initial decision, 0.001 mJ per counted integration
or contraction unit, 5 mJ for a post-observation decision and 0.2/0.3 mJ for range/bearing.
Every schedule has a 500 mJ allowance except the explicitly adverse 2 mJ fixture,
which is rejected before planning starts.
The default search caps are 50000 work units and 255 partition nodes. Exhaustion
suppresses partial certification. These modeled costs omit physical sensing,
propulsion, baseline avionics and actual CPU power; they support no hardware-energy
saving claim. The integrated RequestLedger prevents duplicate/in-flight requests and
charges reserved acquisition costs. The development policy has at most one request. Each requested reading is encoded
to twelve decimal places; this representation error is inside the declared total
sensor-error bound and creates no additional unmodelled precision claim.

There are 13 predeclared engineering contexts and four schedules, all retained.
No held-out outcomes are defined or accessed. Unit fixtures were exposed during
implementation; the full matrix is committed-source development, not preregistration
or a confirmatory population. Source changes after any failed attempt require a
new identity and output directory. Real timing samples are hash-bound but cannot be
expected to replay exactly; deterministic plans, receipts and trajectories must.

## Assumptions that remain outside the result

SA02 bounds are assumed, not physically calibrated. Arbitrary bias drift, unmodeled
fault changes, wrong timestamps and model mismatch can invalidate a nonempty bound
without being detected. The deliberate out-of-model reading case is retained.
The plan cannot assume any requested reading will arrive. Finite protective waiting
is required even when a favourable reading could permit a useful later action.
Real-time operation, repeated feedback performance, target energy and independent
physical validation remain unestablished. SA04 must address execution constraints
without rewriting these records or converting modeled latency into measurement.
