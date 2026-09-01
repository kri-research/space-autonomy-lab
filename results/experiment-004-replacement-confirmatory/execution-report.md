# Experiment 004 replacement confirmatory execution report

## Status

Partition 45 completed the frozen replacement confirmatory campaign: 1,452 paired blocks and 2,904 episodes. The execution used 8 worker processes, completed once, and used no retries, replacement roots, extensions, or outcome-driven adaptation. Partition 44 remains an infrastructure-invalid historical attempt and is permanently retired.

## Reproducibility

The prespecified replay covered 64 paired blocks and 128 episodes. Replay rows were byte-equivalent to the corresponding original rows and the reproducibility gate passed. The canonical episode SHA-256 is `bf1754d89edc2bb06f9b3176e3b29a99bb610412a0437404ddc7b1286432233e`.

## Confirmatory decision

**INCONCLUSIVE.** H1 did not pass because both configurations produced zero physical adverse events across all 1,068 primary paired roots. The gate-minus-reference risk difference was 0, there were zero discordant pairs, and the one-sided exact p-value was 1. H2 was not tested because the prespecified primary gate remained closed.

This is a valid negative/inconclusive confirmatory result. No scientific cell was rerun or tuned after observing the outcome.

## Claim boundary

deterministic planar HCW assurance only; no AI-policy, operational prevalence, flight-safety, 6-DoF, or HIL claim.
