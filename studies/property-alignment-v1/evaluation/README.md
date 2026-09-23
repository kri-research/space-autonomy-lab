# Prospective common-command evaluation

This is the Task 07 design and development pilot. The protected evaluation is
reserved for a separately invoked Task 08. All earlier historical and developmental
records remain unchanged. No outcome in this directory is a flight measurement.

## Scientific question

The surviving candidate distinguishes a checked finite common safe prefix,
a checked HCW first-command obstruction, and unresolved evidence. The primary
quantity is on-time verified diagnostic coverage among individually prefix-qualified
ambiguous information sets. It does not measure complete recovery or controller
superiority. The earlier successful predictive filter remains intact.

## Populations and eligibility

Four equally weighted synthetic strata are fixed before the pilot. The executable
integer/rational distributions, units, joint hypothesis sets, fixed queued inputs
and separate seed-key namespaces are in `generator.py`.

| Stratum | Mechanistic role |
| --- | --- |
| interior_pair | Paired ambiguity with substantial position margin |
| radial_boundary | Opposing side-wall obligations |
| three_face_boundary | Two side walls and outer approach boundary, permitting higher-order conflicts |
| timing_bounded_pair | Two bounded hypotheses, one second age, one second input delay, zero queue and bounded disturbance |

These are deliberately balanced benchmark conditions, not operating frequencies.
All hypotheses must independently admit the known queue and a one-second HCW
continuation from the unchanged 13-action qualification library. Qualification
is sufficient and method-restricted; it is not a full recoverability oracle.
A failed qualification excludes a case before any full-set method runs. A failed
qualification *process* blocks selection rather than inventing ineligibility.
The full set need not have a common continuation; that incompatibility is the
scientific object being tested. No mission completion or abort utility is inferred.

The original midpoint, E004/E005 and Tasks 04-06 never enter this denominator.
The first 32 protected indices per stratum are conservatively retired because
early tests inspected their initial membership. No candidate or qualification
outcome was computed for them. The frozen reserve begins at index 32. Input
identity generation is separated from scientific execution. `exposure_history.json`
records all known exposure, including deliberately repeated calibration fixtures.
Fixed covariance-only, outer-only and reduced-effectiveness stress controls remain
outside the primary population. No learning seeds, hardware sessions or platforms
are invented as independent sampling units.

## Pilot and pre-freeze review

The original pilot contains 48 development cases, 12 per stratum. All qualified;
47 returned on-time rechecked decisions, consisting of 46 common prefixes and
one obstruction. One case remained unresolved. Every attempt is retained in
`recorded_pilot/`. Pilot outcomes may set only the reserve and resource estimate.
The candidate, qualification actions, baseline settings, primary endpoint and
sample count were not tuned to those outcomes.

The original pilot incorrectly called a failed sufficient mean-action check
false-safe. Those raw bytes remain visible. Corrected interpretation retains one
confirmed false-safe shortcut and five unresolved cases, rather than six proved
counterexamples. `pre_freeze_review.json` records this reporting correction.
Both native baselines abstained on all 48 pilot information sets under their hull
and stronger continuation assumptions; this cannot establish candidate superiority.
Their original validation and successful earlier trajectories are preserved.

Eight calibration inputs are repeated for serial, parallel and checkpoint checks.
The final fresh-process coordinator also checks an interrupted start marker and
a forced timeout. These are execution tests, not new independent scientific
replicates. Frozen methods receive no additional outcome-driven tuning.

## Estimand and interval precision

There are 192 selected qualified inputs per stratum and 768 in total. With
alpha = 0.05 and precision target epsilon = 0.05, the classical bound requires
ceil(log(2/alpha)/(2 epsilon^2)) = 738 observations. Balanced fixed chunks give
768 and radius sqrt(log(40)/(2*768)), approximately 0.0490. Five percentage
points is an estimation-resolution target, not a powered difference test,
equivalence margin or operational safety requirement.

The primary binary variable X_i equals one only for an on-time checked delivered
diagnostic. Unresolved, invalid, late, failed and started-but-missing results
remain zero. The inferential interpretation explicitly accommodates dependent
local timing. In fixed stratum/index reveal order let p_i = E[X_i | F_(i-1)].
A conditionally bounded variable satisfies

`E[exp(lambda*(X_i-p_i)) | F_(i-1)] <= exp(lambda^2/8)`.

Iterating conditional expectation gives an exponential bound for the sum.
Markov's inequality and lambda = 4 epsilon give

`P(|mean(X)-mean(p)| >= epsilon) <= 2 exp(-2 N epsilon^2)`.

For completeness, the conditional lemma follows by writing the log moment
function under exponential tilting. Its second derivative is the variance
of a variable supported on an interval of length one, at most 1/4. Integrating
twice from zero gives lambda^2/8. The negative tail uses -lambda.
This proves an interval for the **average conditional success probability**.
A fixed generator-mean interpretation additionally needs independent execution
outcomes. Distinct random keys alone do not establish independent hardware timing.
Neither the 8-case calibration nor one Mac session proves platform reliability.

All secondary results are descriptive, including matched-input status tables,
pairwise/mean shortcuts and native baseline outputs. No pooled McNemar test,
degenerate bootstrap or multiplicity-unadjusted superiority test is used. Missing
selected records cannot shrink the denominator or trigger silent resampling.
Incomplete or unequal strata withhold the balanced inferential interval.

## Frozen execution and preservation

`freeze.py` checks the original pilot, calibration, exact dependency versions and
committed source bytes before producing `frozen/`. Its evaluation ID binds the
complete design, source inventory, component hashes, resources and runtime.
The exact Task 08 command is inside `frozen/freeze.json`; it requires explicit
`--authorize-task08`. The verifier hashes inputs without running qualification,
control or event adjudication on protected cases.

Qualification of the whole reserve finishes before candidate execution. The first
192 eligible inputs per stratum are selected in frozen order. Resume retains exact
receipts; atomic exclusive publication cannot overwrite a completed result.
Started interrupted cases become explicit failures without retries. Unstarted
cases may continue under the same identity. Corruption, source drift, reserve
exhaustion and a failed qualification process stop only affected work.

One evaluation ID is bound to one output location in the private project registry.
The fixed resources are four spawned workers, one BLAS thread each, a 15-second
whole-case watchdog and a 30-minute limit per execution phase. The candidate's
one-second policy budget remains unchanged. Qualification, process startup,
comparison and proof replay are separately identified costs. A watchdog is an
execution safeguard, not an onboard timing theorem or physically safe fallback.

The empty frozen `amendments.jsonl` is part of the immutable identity. Any proposed
change must be appended to a separate amendment record citing the old identity,
with the old directory retained and a new freeze generated. After any outcome
exposure the replacement must carry a new evaluation identity and must not claim
the original protected status for already observed outcomes. A Git deposit and
hashes establish recorded bytes and timing, not independent preregistration or
an independently authenticated absence of outcome access.

## Reproduction

Use the unchanged `protective/requirements.txt` in the isolated baseline environment.
From the study root run `python -m pytest evaluation/tests` for development-only
tests and `python -m evaluation.verify --freeze evaluation/frozen/freeze.json` for
read-only identity verification. The CI workflow never runs the protected campaign.
No historical release, manifest, result or manuscript source is modified here.

## CI timing and the pre-execution amendment

The first freeze is preserved unchanged in `retired_freezes/` and superseded before any protected execution. Shared-runner CI exposed an allowed one-second policy-budget miss, so exact equality of live-clock serial and parallel results is not a valid universal assertion. The mechanics tests now run real numerical methods using calibration-only deterministic child policy clocks. Parent process watchdogs, explicit timeout tests and late-answer rejection still use their specified checks. The existing real-clock calibration is a recorded observation, not a guarantee of timing equivalence. No candidate method, decision budget, population, endpoint or protected sample size changed. `amendments.jsonl` records the correction and the new freeze binds the revised test source inventory.
