# Experiment 004 confirmatory result

Experiment 004 evaluates the planar HCW assurance architecture under the prospectively frozen replacement confirmatory design. The original partition-44 attempt was invalidated by infrastructure timeout before inference and is permanently retired. Partition 45 is the sole valid replacement confirmatory execution.

The replacement campaign completed 1,452 paired blocks and 2,904 episodes using the frozen 8-process runner. It completed once, with no retries, replacement roots, sample-size extension, or outcome-driven adaptation. The prespecified 64-block / 128-episode replay was byte-equivalent and the reproducibility gate passed.

The confirmatory decision is **inconclusive**. In the 1,068 primary paired roots, both the reference and monitor-gated configurations had zero physical adverse events. H1 therefore did not establish safety superiority: risk difference 0, zero discordant pairs, one-sided exact p = 1. H2 was not tested because the prespecified primary gate remained closed.

This is retained as a valid negative/inconclusive result, not repaired or rerun. Its scope is deterministic planar HCW assurance only; it does not establish operational prevalence, flight safety, 6-DoF validity, HIL validity, or evidence about a learned AI policy.
