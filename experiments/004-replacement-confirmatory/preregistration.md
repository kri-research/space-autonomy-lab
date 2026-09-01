# Experiment 004 replacement confirmatory preregistration

_Pre-outcome replacement freeze; partition 45 remains reserved and unmaterialized._

## Why a replacement is scientifically permissible

The original partition-44 campaign was terminated by an external 14,400-second execution limit after 602 of 2,904 planned episode rows. The frozen fixed-cell gate closed before H1 or H2, no replay was performed, and no partial outcome was used for inference or for this replacement design. Partition 44 is permanently retired; its audit identity is recorded in `experiments/004-invalid-partition-44/audit.json`.

This replacement changes execution infrastructure only. It preserves the original Experiment 004 confirmatory scientific question, deterministic planar HCW model, two configurations, case matrix, 1,452 paired blocks, 2,904 episodes, primary hypotheses, estimands, thresholds, analysis rules, and 64-block/128-episode replay. A fresh disjoint seed namespace, partition 45, is used.

## Frozen execution protocol

Each paired root block is an independent process-pool work unit. The default worker count is 8 on the 15-logical-CPU validation host, selected prospectively from outcome-blind performance evidence. `--workers` may be set explicitly for another host without changing any scientific cell.

Every completed paired block is written atomically to a content-hashed checkpoint shard bound to the frozen campaign identity. Worker completion order cannot affect the final result: final episode output is assembled only in frozen ascending block order. Existing shards are hash-verified before use; corrupt, duplicate, foreign, or mismatched shards fail closed.

An infrastructure restart may continue the same frozen partition-45 campaign by verifying completed shards and computing only missing blocks. This is checkpoint continuation of identical prospectively frozen scientific cells, not outcome-driven retry, replacement, extension, or sample-size adaptation. Completed valid blocks are never recomputed. No partition-44 block may execute.

The campaign command is deliberately run without a finite outer shell timeout. Progress is durable at paired-block granularity.

## Analysis contract

H1 and H2, the primary population, case weights, adverse-event definition, hold-loss definition, exact paired tests, alpha levels, minimum reportable effect, mission-harm margin, missing-cell validity rule, and replay selection are unchanged from the original frozen Experiment 004 confirmatory preregistration.

No partition-44 partial efficacy result informed this replacement. No new secondary efficacy family is introduced. No outcome-dependent exclusion, subgroup, replacement root, additional sensitivity, or sample-size change is allowed.

## Evidence boundary

The claim remains bounded to the deterministic planar HCW assurance testbed. It is not a 6-DoF, flight-safety, certification, hardware-in-the-loop, or learned-policy validation claim.
