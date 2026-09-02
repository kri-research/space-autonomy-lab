# Experiment 005 nonlinear-truth transfer-pilot preregistration

_Design and mechanics calibration only; partition 52 remains unmaterialized and partition 53 remains untouched._

## Purpose and interpretation boundary

This pilot is a non-inferential engineering design validation of whether the frozen Experiment 004
planar HCW controller, two navigation filters, estimated-geometry monitor, vector actuation path,
fault routing, offline event evaluator, and checkpointed process-pool runner remain mechanically
connected when physical truth is the frozen Experiment 005 nonlinear two-body chief/deputy model.

It is not sized or tuned to find hazards, favorable architecture effects, superiority,
noninferiority, or an operational event rate. No Experiment 004 outcome, including its zero-hazard
confirmatory result, was used to choose the challenge magnitudes, gates, horizons, case count, or
root count. The transferred challenge magnitudes are byte-bound to the pre-existing Experiment 004
pilot design inputs and are retained only to test the same plumbing under a different truth model.

Partition 51 may reveal only feasibility, numerical or event sensitivity, horizon practicality,
model-mismatch observability, estimator/controller plumbing, information boundaries, deterministic
execution, and intended fault/domain activation. Architecture contrasts, hazard discordance, and
comparative outcome effects are prohibited calibration inputs.

## Frozen foundation

The design requires foundation freeze
`921c481726d6f078621ff3a355a7803af803bdc61a8a2da07ffb974a433b3be8`, readiness
`9ec734543fd3580e9a2990a16dc56747a0f75334f76bd2c7ae1fdc3647732e67`, and status
`READY_FOR_DESIGN_VALIDATION_PILOT`. Every foundation source hash is rechecked without changing a
foundation byte.

Physical truth is the frozen 12-state nonlinear central-gravity pair propagated by bounded RK4.
Online estimation, control, and monitor prediction remain the frozen four-state planar HCW model.
Truth, event classifications, root identity, challenge identity, and evaluator state are unavailable
to online components.

## Frozen matrix

The ten cases are:

1. nominal transfer;
2. a no-fault transfer-envelope corner that makes nonlinear-versus-HCW mismatch observable;
3. a deterministic nonlinear truth-space keep-out crossing fixture;
4. primary navigation bias;
5. primary navigation dropout;
6. monitor navigation bias;
7. monitor-logic false trip;
8. shared-cause navigation bias;
9. actuation effectiveness loss; and
10. an additive LVLH disturbance burst.

Every root is executed through `primary_reference` and `independent_monitor_gate` as paired
diagnostics. Pairing does not create a treatment comparison: no configuration difference, ranking,
or architecture effect may be estimated or claimed.

The ordinary initial along-track bound is prospectively narrowed from the historical E004 pilot's
`[-105, -95] m` to `[-100, -95] m`. This is a geometry-validity correction, not an outcome-tuned
change: the frozen E005 truth evaluator fails closed below the approach-set boundary at `-100 m`.
The fixed mismatch case uses the foundation transfer-envelope corner
`[x,y,vx,vy]=[10,-100,0.14,-0.14]`. The truth-event fixture uses a one-second unforced crossing from
`[x,y,vx,vy]=[0,-12,0,4]`; it is an event-classification fixture, not an operational challenge.

## Outcome-blind sample count and replay

Candidate root counts were `[1, 2, 4]`. One root cannot place both diagnostic configurations in both
within-block order positions. Two roots are the first count that gives each configuration one
appearance in each order position for every case while covering every frozen case/domain. Therefore
the pilot has 2 roots per case, 20 complete blocks, and 40 future episode rows. This is a coverage
argument, not a statistical-power calculation. Additional roots, replacement roots, and
outcome-dependent extension are forbidden.

The replay subset is replicate 0 in all ten cases: 10 blocks and 20 episodes, fixed before partition
52 exists. Replay requires byte-identical canonical rows and trace digests on the frozen
runtime/platform.

## Model-mismatch reporting

For every future episode, nonlinear truth is compared descriptively with a one-second HCW prediction
that receives the same online commanded input. The fixed no-noise/no-fault mismatch case requires
120 finite observations and at least one positive residual, which proves observability. There is no
absolute favorable or unfavorable mismatch threshold. Residual sign or magnitude cannot be used as
an architecture endpoint.

## Conjunctive pilot gates

A future partition-52 pilot passes design validation only if all frozen gates pass:

- exact 10-case by 2-root by 2-configuration completeness;
- no duplicate, missing, extra, foreign, replacement, or historically overlapping roots;
- finite nonlinear truth and relative states under the frozen RK4 contract;
- finite estimator covariance, minimum eigenvalue at least `-1e-12`, and trace below `1e6`;
- correct nonlinear truth-space keep-out-only event classification in the fixed fixture;
- intended model-mismatch, navigation, monitor-logic, shared-cause, actuation, and disturbance
  activation with unaffected channels remaining inactive;
- source-inspected controller/monitor information boundaries with no truth or evaluator input;
- zero infrastructure failures, retries, and replacement roots; checkpoint continuation may execute
  only missing unpublished cells after every existing shard validates;
- deterministic replay of the frozen subset; and
- descriptive mechanics-only reporting with no inferential architecture claim.

## Seed and execution contract

PCG64DXSM uses
`SeedSequence([5005, partition, geometry_case, challenge_case, replicate, stream])`. Partition 51 is
complete mechanics calibration only. Partition 52 is authorized for one future write-once
materialization only after this design freeze independently verifies. It remains unmaterialized and
unexecuted in this task. Partition 53 remains untouched, with no design, hypothesis, size,
materializer, runner, seed path, result path, or root row. Partition 951 remains deterministic
validation only.

The future runner retains the foundation architecture: frozen contiguous schedule, process pool,
campaign-bound content-hashed shards, same-directory no-clobber publication, fsync where supported,
exclusive lock, complete pre-submit shard validation, missing-cell-only continuation, canonical
assembly, and fail-closed handling of corrupt, foreign, duplicate, noncanonical, or conflicting
evidence.

## Next task

Only after this freeze is merged may a separate task materialize and execute partition 52 exactly
once. No confirmatory design or partition-53 work is authorized.
