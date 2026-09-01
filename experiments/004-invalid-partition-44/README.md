# Experiment 004 invalid partition-44 attempt

The first confirmatory execution was terminated by an external 14,400-second infrastructure limit before the frozen campaign completed. It produced 602 durable episode rows (301 complete paired blocks) of 2,904 planned rows. The fixed-cell validity gate therefore closed before H1 or H2.

No retry, resume, replacement, extension, imputation, replay, or partial-outcome inference was performed. Partition 44 is permanently retired. `audit.json` records the exact counts and SHA-256 identities needed to audit this invalid attempt without publishing partial efficacy results.

A replacement confirmatory protocol uses a fresh disjoint seed partition and unchanged scientific hypotheses, estimands, case matrix, sample size, and analysis thresholds.
