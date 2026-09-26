# SA03 development results

Source commit `6ee881a13904e7d5e3cc04615f8d8e5d5225daff`. One recorded development execution contains all thirteen named contexts and four schedules, fifty-two comparisons. Unit fixtures were exposed during implementation. This is not a held-out population, operational reliability study or a controller-superiority experiment.

## Complete selection results

Each entry gives the selected sensor (or no request) and whether every retained timely reading branch has a checked useful action. For no request, the usefulness label concerns its common action. Missing readings have separate protected, potentially non-useful continuations. An all-reading usefulness label does not imply actual delivery or mission success.

| Context | Fixed range | Fixed bearing | Uncertainty-triggered | Decision-aware |
| --- | --- | --- | --- | --- |
| alongtrack_ambiguity | range, useful | bearing, usefulness unproved | range, useful | range, useful |
| radial_ambiguity | range, usefulness unproved | bearing, useful | bearing, useful | bearing, useful |
| shared_bias_ambiguity | range, usefulness unproved | bearing, usefulness unproved | range, usefulness unproved | no request, usefulness unproved |
| already_goal_eligible | range, useful | bearing, useful | no request, useful | no request, useful |
| existing_action_adequate | range, useful | bearing, useful | bearing, useful | no request, useful |
| velocity_ambiguity | range, usefulness unproved | bearing, usefulness unproved | range, usefulness unproved | no request, usefulness unproved |
| declared_late_range | no request, usefulness unproved | bearing, usefulness unproved | no request, usefulness unproved | no request, usefulness unproved |
| missing_requested_observation | range, useful | bearing, usefulness unproved | range, useful | range, useful |
| underestimated_range_delay | range, useful | bearing, usefulness unproved | range, useful | range, useful |
| unsafe_wait | unresolved | unresolved | unresolved | unresolved |
| model_work_budget_exhaustion | resource_exhausted | resource_exhausted | resource_exhausted | resource_exhausted |
| partition_budget_exhaustion | resource_exhausted | resource_exhausted | resource_exhausted | resource_exhausted |
| unmodelled_range_bias | range, useful | bearing, usefulness unproved | range, useful | range, useful |

## What improved and what did not

The decision-aware policy selects range for along-track ambiguity and bearing for radial ambiguity. Both choices support useful actions for every modeled timely reading. However, the simple uncertainty-triggered rule makes the same choices and applies the same commands on these cases. Their squared-distance changes are respectively -0.002993749698 and -0.002992516303 m2 on the retained realized trajectories. No superiority to the simpler rule follows.

The existing-action case is a limited useful difference: the decision-aware rule requests no measurement and applies the same action as the three sensing comparators. Its modeled cost is 5.094 mJ, versus 10.95 mJ for the uncertainty-triggered rule. Those figures follow an illustrative work-accounting model; they are not measured spacecraft energy. The already-goal-eligible case needs no request for either adaptive rule.

The shared-bias and velocity-ambiguity cases cannot establish useful actions for every reading leaf. The decision-aware rule therefore retains the checked no-observation action. Requesting less information does not automatically mean better performance: fixed range and the uncertainty rule achieve larger realized task progress in those two cases, despite lacking a universal usefulness certificate. Searching both channels also costs more computation, so avoiding a request can still be computationally expensive.

## Retained adverse cases

A declared range delay that misses application is rejected as a sensing option. The actual missing and underestimated-delay cases use the previously checked no-observation action. No useful progress is recorded there for the decision-aware rule. The stored all-reading usefulness claim is expressly conditional on a timely in-model reading and is not transferred to the missing branch.

The unsafe-wait context returns unresolved under all four schedules; all four realized traces leave the research geometry. Favorable hypothetical readings cannot erase that interval. The low-energy and three-node cases remain resource-exhausted without a certificate. The low-energy case performs no planning work. The node-limited case retains its partial computational cost and does not promote an incomplete tree.

In the unmodeled 0.5 m range-bias case, fixed range, uncertainty-triggered and decision-aware dispatch select a branch whose application-time enclosure excludes the realized numerical state. The incorrect sensor assumption is not detected from that in-support reading. The particular trajectories still remain contained and decrease target distance; this does not repair the invalid branch-membership assumption or support an unconditional safety claim.

There are 40 complete conditional plans and 12 uncredited outcomes across the named matrix. The realized model containment check succeeds in 48 of 52 cells, with the four unsafe-wait failures retained. Only the four already-goal-eligible cells prove two seconds of dwell, starting in the goal. None demonstrates acquisition from an initially different target state. These totals describe the fixture set only and are not probabilities or evidence of general controller ranking.

## Exact analytical results

The disturbance-free symmetric scalar example gives a latest maximum-braking application of 1.25 s and latest observation acquisition of 1 s for the stated 0.25 s delay. Exact boundary, later-but-still-contained waiting, unsafe waiting, overlapping observation supports, a nuisance-label reduction and an already adequate action are retained in analytical.json. The scalar result assumes the identifying observation is delivered; it does not certify the spacecraft missing-reading branch or full HCW recovery.

## Measured execution costs

| Schedule | Requests in 13 contexts | Planner median ms | Planner maximum ms | Planner calls exceeding 50 ms |
| --- | ---: | ---: | ---: | ---: |
| fixed_range | 9 | 290.841500 | 1773.837458 | 10 |
| fixed_bearing | 10 | 267.229375 | 1214.535583 | 11 |
| uncertainty_triggered | 8 | 276.657125 | 1971.513833 | 10 |
| decision_aware | 5 | 386.946000 | 2710.298042 | 9 |

All 52 planner samples and 52 complete selected-tree recheck samples are retained. 40 planner calls exceed the modeled 50 ms planning phase; maximum measured planner duration is 2710.298042 ms. Samples come from one Darwin arm64 host execution with CPython 3.13.5, not independent target processors. Failed and early-return calls are included, so the medians must not be interpreted as successful-control throughput.

The observation-tree prototype is not ready for literal real-time use at the modeled clock. Rechecking at dispatch is measured separately and also incurs cost. Simulation output does not shift its application slot to hide these overruns. No WCET, energy measurement, physical protection or mission hardware result is claimed.

## Reproduction and continuation

All inputs, context identities, complete trees, receipts, simulated dispatches, evaluation traces, analytical results and host timing samples are retained. Deterministic outputs must reproduce exactly; fresh timing durations are not expected to match. The manifest binds source bytes and modes to the actual Git blobs and the committed record identity.

SA03 delivers a sound bounded-model candidate and explicit failure limits. The simpler uncertainty-triggered rule remains the preferred comparison baseline for SA04 because it obtains the same supported sensing choices on the two principal ambiguity examples at lower planning cost. The decision-aware early check can avoid unnecessary sensing when an adequate action already exists. No general benefit over the simpler rule or the published active-sensing literature is established. SA04 must address measured execution costs before using either approach as a literal real-time implementation. The existing SA01/SA02 results and all historical science remain unchanged.
