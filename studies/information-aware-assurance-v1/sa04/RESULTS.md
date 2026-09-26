# SA04 execution results

Source commit `0ada9b66ab85a304d400b5b4b07dc02b4bc1b181` was committed before the complete recorded execution.
This record contains 32 exposed deterministic integration fixtures, 36 diagnostic
host trials in three process sessions, six retained warmups and twelve separate
deadline-enforced trials. These are engineering observations, not a held-out
population, operational reliability estimate or independent hardware replication.

## Actual scoped host measurements

Diagnostic calls measure the full IPC path without dispatch authority. Each group
below has six samples. Times include serialization, worker execution and response
validation; observer and checker/planner components remain separately recorded.

| Context | Policy | Planner median ms | Planner max ms | Checker median ms | Checker max ms |
| --- | --- | ---: | ---: | ---: | ---: |
| ambiguity | uncertainty_triggered | 418.107000 | 430.740208 | 19.691021 | 26.936250 |
| ambiguity | decision_aware | 659.613646 | 695.545083 | 19.168458 | 20.428792 |
| adequate | uncertainty_triggered | 17.168791 | 19.948209 | 17.203250 | 18.411250 |
| adequate | decision_aware | 17.410041 | 18.637750 | 17.054187 | 19.432875 |
| unsafe | uncertainty_triggered | 1.657230 | 1.982542 | 5.250500 | 5.557291 |
| unsafe | decision_aware | 1.678292 | 1.920584 | 4.989167 | 5.565167 |

All 36 diagnostic calls completed without transport failure. Twelve complete planning
phases exceeded the inherited 50 ms budget; none of these diagnostic checking phases
exceeded it. The checker is a different, smaller realized-action obligation than the
previous complete future-outcome tree, so these are not like-for-like superiority
measurements. The unsafe context returns early without a valid protection result.
Its low timings must not be interpreted as successful-control throughput.

Across all diagnostic contexts, the complete compute-path median is
35.047770 ms, nearest-rank p95 is 694.783001 ms,
and maximum observed is 715.285250 ms. This directly measured parent interval
excludes separately recorded offline arming and process startup; component sums and
remaining Python/cleanup overhead are retained. It includes neither a measured
physical sensor delay nor real actuator latency.

## Deadline enforcement

The twelve fresh-process enforced trials retained six planner timeouts and four checker
timeouts (categories can overlap). Two further complete checker returns were refused
because admission itself finished after 700 ms. Starting validation before a deadline
does not count as completing it. No late candidate was silently retimed.

Only two virtual candidate signals were emitted, both in the already-adequate context
and both zero acceleration. There were **zero nonzero candidate signals**. These two
events are therefore not effective interventions or demonstrated mission progress.
All emitted signals had pre/post timestamps within the separately verified [700,710]
ms initiation window. The other trials continued only the prearmed finite simulated
coast, under its own entry and model assumptions. No physical signal was emitted.

Thus the fresh-process complete loop has not demonstrated dependable operation under
the 50 ms planning/checking budgets. Warm diagnostic timings do not erase cold-path
failures. The measured host is not a dedicated target processor, and none of these
maxima is a worst-case execution-time proof.

## Resources and scope

Measurements used CPython 3.13.5 on one Darwin arm64 host. Ambient load and logical
CPU count are retained, without imposing an artificial stress load. Diagnostic
planner startup ranged from 32.298625 to 51.754416 ms; checker startup from
31.772833 to 39.905083 ms. All additional enforced-trial startups are recorded.
Maximum offline arming duration across diagnostics/warmups was 21.673333 ms.

Maximum observed parent, planner and checker process RSS were respectively
33,456,128, 29,425,664 and 29,310,976 bytes. These are process high-water marks, not
incremental allocation or onboard-memory requirements. Maximum diagnostic/warmup
write-and-flush logging cost was 2.197667 ms. No durable-storage fsync timing or
physical energy was measured. CPU durations do not become energy savings.

## Failure handling and mathematical checks

Both policies were exercised over all sixteen named integration fixtures. Valid entry
is required before a fallback receives credit. The two unsafe-initial cases remain
unprotected and their realized trajectories leave the research geometry. The other
thirty realized trajectories remain contained in these examples only; this is not
a population safety probability. All thirty-two traces end explicitly after expiry.

Late or failed planning/checking, a corrupted checker channel, unsupported sensor
timing and an out-of-model bias do not authorize a candidate. A missed initiation
window does not move the command later. Reported setting/saturation faults and loss
of expected acknowledgement remove affected credit. Saturation is a reported
capability-invalidation injection, not an experiment on physical actuator hardware.
The out-of-model sensor example is retained; detecting this instance does not imply
detection of every violated sensor bound.

Tests also exercise duplicate/reordered sessions, truncated/corrupted frames, excessive
payloads, nonfinite/numerically hostile inputs, changed histories/models, a stale
estimate, expired results and future/missing live context. Semantic replay detects
forged timing, outdated certificates and an unchanged fallback falsely called an
intervention even when trace hashes are locally recomputed. Independent rational
HCW point bounds corroborate the new initiation-band enclosure on small fixtures.

The live-context omission and shared mutable model alias were reproduced by failing
regressions and corrected before source freeze. Reordered-trace error handling was
also corrected; completion of admission itself is now included in the real deadline.
Earlier implementation, scientific and recorded phase files are unchanged.

## Continuation gate

SA04 supplies a tested software execution boundary and reconstructable evidence for
its explicitly represented environment. It does not establish real-time usefulness
of the full planning path. SA05 may evaluate the software with explicit simulated
timing and energy assumptions, retaining this negative host finding. Actual target
latency, sensor calibration, low-level command termination/watchdog behavior, energy
and physical or external validation remain unperformed. No SA05 execution is started.
