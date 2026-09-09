# Experiment 005 corrigendum

Issued 9 September 2026. Applies to the E005 narrative associated with Space Autonomy Lab
v0.1.0, software commit `f0e9e5d8c140ca3d5eea71cee97fd29f23bffe12`.

## Correction

The original E005 closeout incorrectly states that neither configuration produced a physical
adverse event. Zero beneficial and harmful **discordant pairs** were incorrectly interpreted as
zero **absolute adverse episodes**. The recovered records and the unchanged frozen analysis
establish the following counts in the two-case synthetic partition-53 population.

| Case | Configuration | Episodes | Collision | Keep-out entry | Corridor departure | Composite adverse | Hold acquired |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Primary-navigation bias | Primary reference | 534 | 0 | 0 | 534 | 534 | 534 |
| Primary-navigation bias | Independent-monitor gate | 534 | 0 | 0 | 534 | 534 | 534 |
| Primary-navigation dropout | Primary reference | 534 | 0 | 0 | 534 | 534 | 534 |
| Primary-navigation dropout | Independent-monitor gate | 534 | 0 | 0 | 534 | 534 | 534 |
| **Total per configuration** | **Primary reference** | **1,068** | **0** | **0** | **1,068** | **1,068** | **1,068** |
| **Total per configuration** | **Independent-monitor gate** | **1,068** | **0** | **0** | **1,068** | **1,068** | **1,068** |

These are **recorded evaluator flags**. The frozen composite is collision OR keep-out entry OR
corridor departure. The complete paired adverse table is:

| Paired outcome | Roots |
| --- | ---: |
| Both safe | 0 |
| Reference adverse, gate safe | 0 |
| Gate adverse, reference safe | 0 |
| Both adverse | 1,068 |

The unchanged frozen H1 calculation returns risk difference 0.0, exact one-sided p = 1.0,
zero discordances and H1 failure at alpha 0.025 with the required observed reduction of at least
five percentage points. H2 remains **not formally tested** because H1 closes the gate; its
observed gate-induced hold-loss count, 0/1,068, is descriptive. The comparative decision remains
**INCONCLUSIVE**. This establishes neither superiority nor equivalence, zero risk or mission safety.

## Evidence and method

The [dated supplement](../supplements/2026-09-09-evidence-reconciliation/README.md) contains the
1,092 recovered original files in a lossless archive, a per-member inventory, and
[newly dated reconciliation output](../supplements/2026-09-09-evidence-reconciliation/e005-reconciliation.json).
The campaign has 1,068 paired roots and 2,136 rows. Each case has 534 roots. Strict type and
membership checks precede the unchanged `analyze_confirmatory_rows(rows, seeds, study)` function.
Its fixed-cell checks pass. Absolute counts and the complete paired table were also counted
independently and agree with the frozen analysis.

The source is the frozen design commit `d841a016361974734bd28b27ff39e9df0e2cbaed`, freeze ID
`1acd0af2246fb5ba1e86da0302f6b7f3cda57e59018068186375507000d264ca`.
The output records source, configuration, data, method-script and environment identities. It was
computed after release using CPython 3.11.16, NumPy 2.4.6 and SciPy 1.17.0. It is explicitly dated
as a post-release recomputation. No original final `analysis.json` was recovered or fabricated.
The original execution summary retains `EXECUTION_COMPLETE_PENDING_FROZEN_CONFIRMATORY_ANALYSIS`.

The 16 paired stored replay blocks contain 32 rows. Their selection agrees with the frozen
first-eight-roots-per-case rule, and their bytes match the corresponding stored campaign rows.
**No new simulation campaign or simulation replay was executed.**

## Meaning of the corridor flag

Static tracing of the original implementation establishes the following interpretation:

* `experiment_005/dynamics.py` converts chief/deputy inertial states into target-centred rotating
  LVLH coordinates. Positive x is radial outward, positive y is along-track and positive z is
  orbit-normal. Position is in metres; rotating relative velocity is in metres per second and
  includes the angular-velocity cross-product correction.
* `experiment_005/geometry.py` defines an admissible position union. The closed approach corridor
  spans y = -100 to -30 m, with radial half-width decreasing linearly from 10 to 3 m. The closed
  hold ellipse is centred at (0, -30) m with radial/along-track half-widths (2, 3) m. Positive
  signed excess above 1e-9 m sets the corridor-departure flag. This excess is a signed set test,
  not a general Euclidean distance-to-boundary measurement.
* `experiment_005_transfer_pilot/runner.py` passes each 0.25-second realised truth segment to the
  evaluator across the 300-second horizon. The geometry search uses 65 nodes and bounded local
  refinement, including segment endpoints. The evaluator OR-latches any departure, including
  initial or transient departures. The final boolean is copied into the episode dataclass and
  serialised unchanged; the confirmatory wrapper changes only schema and phase labels.
* Hold acquisition separately requires at least 60 continuous seconds inside the hold ellipse
  at speed at most 0.05 m/s. An earlier departure and later hold acquisition can coexist.

Direct algebra on stored initial positions finds all 1,068 within the specified admissible union.
Recorded maximum excesses span approximately 1.3994 to 2.9249 m, minimum separations 22.6402 to
24.9924 m, and maximum hold dwells 122 to 138 seconds. These are existing summaries, not newly
propagated trajectories. The retained archive has trace digests and summaries but no complete
per-segment trajectory history; exact event times and trajectory causes are not reconstructed.

## Limits and preserved history

Fixed-cell PASS checks record completeness, required fields, fault activation, covariance bounds,
attempt status and stored numerical-validity flags. It does not independently authenticate custody
or validate the physical evaluator. The geometry search is numerical sampled/refined evidence,
without a formal guarantee that every possible extremum is captured. The corridor union uses
radial and along-track position; cross-track values are recorded as zero in this planar study.
No six-degree-of-freedom or general three-dimensional envelope claim follows.

The data are recovered from retained execution files with internally consistent hashes, schedules
and checkpoint links. Filesystem timestamps and self-hashes do not independently authenticate
historical execution or rule out unrecorded activity. Literal no-retry/no-extension booleans in
the frozen analysis are not independent proof of those governance claims.

The boundary remains two synthetic nonlinear central-gravity cases, deterministic reference
control and independent-monitor comparison. No operational-prevalence, flight-safety, hardware,
learned-policy or KRI-STD-001 conformance claim is made. This review identifies no proven sign,
unit or serialisation defect that justifies erasing the flags; it also does not independently
revalidate physical trajectories.

The original [closeout Markdown](experiment-005-confirmatory-closeout.md),
[closeout JSON](experiment-005-confirmatory-closeout.json), [release notes](release-v0.1.0.md)
and all frozen scientific bytes remain intact. This notice supersedes the E005 zero-absolute-event
assertion wherever repeated in the historical benchmark guide, KRI-STD-001 mapping, public demo
guide, research roadmap and original release body. Their historical bytes are preserved; use
this notice when citing them. E004's zero-event **primary-population** result is unchanged, as are
its separate adverse-event strata. No new experiment or software release is introduced.
