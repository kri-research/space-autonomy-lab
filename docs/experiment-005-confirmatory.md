# Experiment 005 partition-53 confirmatory design

## Status

This is a prospective design freeze only. Partition 53 remains unmaterialized and unexecuted. The
generator is authorized only after exact freeze verification; it was not invoked here. The earlier
NOT READY blocker audit remains preserved unchanged.

## Question and design

The study asks whether the frozen independent-monitor gate reduces the paired risk of independently
evaluated physical collision, unauthorized keep-out entry, or corridor departure relative to the
same deterministic vector LQR reference in an equal-weight nonlinear-truth population of primary
navigation bias and primary packet dropout, while keeping gate-induced loss of hold acquisition
below 5%.

Only the two frozen primary cases enter the inferential population: 534 roots each, for 1,068 paired
blocks and 2,136 episodes. H1 is an exact one-sided paired-discordance test at alpha 0.025 plus a
minimum observed 5 percentage-point net reduction. H2 is a gatekept exact one-sided binomial test of
gate-induced hold loss below 0.05 at alpha 0.025. All other recorded quantities are descriptive and
non-rescuing.

The sample size is the smallest even count reaching 90% exact power for a prospective 10
percentage-point net reduction under the variance-worst all-discordant paired-binary construction.
It reproduces the pre-outcome Experiment 004 basis and uses no partition-54 effect, rate, direction,
or discordance estimate.

## Execution boundary

Partition 53 uses the disjoint root namespace `experiment005:53:<case_code>:<replicate>` and frozen
streams 201-207. Replicates 0-7 in each case form a 16-block/32-episode deterministic replay subset.
Materialization and result paths are write-once. Content-hashed complete-block checkpoints may
continue only after an interruption without a terminal worker failure; valid blocks are never
recomputed. Failures, corruption, missing cells, retries, root replacement, imputation, adaptive
extension, endpoint switching, and outcome-dependent changes all close inference.

The claim is bounded to the two-case synthetic nonlinear central-gravity testbed. A null, harmful,
or inconclusive result is allowed. This design does not estimate operational prevalence, qualify
flight safety, validate six-degree-of-freedom or hardware-in-the-loop behavior, or support a
learned-policy claim.
