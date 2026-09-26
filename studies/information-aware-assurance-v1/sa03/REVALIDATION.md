# SA03 causal receipt revalidation

Corrected source commit `914914546f0a19f499dce59083206c7f0b9a858e`. The first source, first execution in `recorded/`, and its `RESULTS.md` remain unchanged. This is a separately identified correction and full development revalidation, not another independent population.

## Defect and correction

A generated observation with an availability time after dispatch had been passed across the online interface. The original dispatcher did not directly use its reading, but its online status revealed the unavailable receipt. A further adversarial check reproduced a stronger failure: adding a future conflicting duplicate changed an available-reading action to fallback. The original-source negative control failed as expected; the corrected implementation filters unavailable receipts before conflict handling and passes both regressions.

The simulation now records actually delivered receipts separately from generated evaluation-only receipts. These are causal-interface changes. The physical model, thirteen contexts, four schedules, candidate command menu, partition rule, protection horizon, resource formula and analytical examples are unchanged.

## Complete comparison with retained evidence

All 52 contexts/policies and all 52 realized evaluation trajectories match the first execution exactly. All summary fields match except the dispatch reason in three underestimated-range-delay cells (fixed range, uncertainty-triggered and decision-aware). These now correctly report the no-observation action rather than reporting knowledge of an unavailable late packet. Their applied actions, enclosures, task change, protection and costs are unchanged.

The corrected set retains 40 complete conditional plans, 12 uncredited outcomes and model containment in 48 of 52 realized trajectories. The four unsafe-wait failures remain. Only the four already-goal-eligible cases prove the two-second dwell; no acquisition from a different initial target is demonstrated. The three nonempty state exclusions under the deliberately unmodeled range bias remain explicit.

The decision-aware and simple uncertainty-triggered schedules choose the same useful sensors and commands on the along-track and radial ambiguity examples. The candidate avoids an unnecessary request when an existing useful action is already available, but can cost more planning work and can be more conservative in realized task progress. No general advantage or state-of-the-art superiority is established.

## New host timing observations

| Schedule | Requests | Planner median ms | Planner maximum ms | Planner over 50 ms | Recheck maximum ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| fixed_range | 9 | 302.974792 | 1884.211084 | 10 | 1684.959375 |
| fixed_bearing | 10 | 282.517208 | 1016.496417 | 11 | 948.285584 |
| uncertainty_triggered | 8 | 371.225208 | 1813.346834 | 10 | 1826.175167 |
| decision_aware | 5 | 398.418042 | 2832.573416 | 9 | 349.883250 |

All 52 planner and 52 selected-tree recheck samples are retained in this execution. 40 planner calls exceed the assumed 50 ms planning phase; the maximum is 2832.573416 ms. Measurements are from one Darwin arm64 host using CPython 3.13.5. They are not target-processor measurements, independent hardware repetitions or a worst-case bound. The original timings remain separately available and are not pooled into a favourable estimate.

Rechecking uses the same full-tree machinery and itself takes material time. Both planning and rechecking remain offline computations for this stage. The illustrative simulated application clock cannot be used as evidence of real-time feasibility or physical energy savings.

## Additional adversarial and mathematical checks

The expanded tests retain the exact scalar latest-useful-observation condition, closed reading-support boundaries, missing-reading protection, invalid assumptions, false obstruction prevention, complete partitions, request repetition and exhaustion. Additional coupled fixtures combine nonzero queued control, actuator uncertainty, bounded disturbance, common/channel bias and acquisition-time extremes; every matching leaf retains the tested state and coherent bias. One failed live branch and loss of the no-observation action prevent universal protection. A measurement-conditioned SA02 estimate also connects to the complete policy. These finite tests corroborate the documented conditional argument; they are not a second full estimator/checker implementation or physical validation.

## Reproduction and SA04 boundary

Run `python -m sa03.artifact verify sa03/recorded_causal --replay` in the documented full-history checkout and isolated environment. Source bytes and modes are checked against actual Git blobs; record membership and manifest identity are anchored to the committed record. Every deterministic comparison must replay, while newly measured timing durations need not match.

The supported next-stage starting point is the simpler uncertainty-triggered schedule with the candidate retained as a bounded research comparison. An already-adequate-action check is a promising separate optimisation; a combined deployment policy has not been evaluated here. SA04 must establish deadline-aware execution and resource accounting before either method can be claimed to operate at the modeled clock. External mission review, calibrated sensors, target hardware and repeated-feedback performance remain unperformed. No SA04 work is started by this revalidation.
