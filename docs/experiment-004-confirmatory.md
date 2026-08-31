# Experiment 004 confirmatory assurance design

This milestone freezes a prospective deterministic-controller assurance comparison on the planar
HCW foundation. It does **not** train or validate an AI policy and does not materialize partition 44.

The primary population is the equal-weight mixture of the frozen primary-only navigation-bias and
primary-only dropout strata. It compares `independent_monitor_gate` with `primary_reference` on the
independent evaluator's physical endpoint (collision, unauthorized keep-out entry, or corridor
departure), followed by a gatekept 5% mission-harm risk limit for hold acquisition. Monitor-only,
shared-cause, actuation, disturbance, nominal, and technical mechanisms remain separate and are
non-rescuing.

Frozen size: **1,452 paired blocks / 2,904 episodes**. Primary size is 1,068 roots (534 per primary
stratum), selected by an exact worst-case paired-binary calculation without a partition-43 effect
estimate. The fixed outcome-blind replay subset is 64 blocks / 128 episodes.

See `experiments/004-confirmatory/preregistration.md` for the complete estimand, gatekeeping,
failure, seed, and write-once execution contract.
