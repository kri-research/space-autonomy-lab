# Experiment 002b corrective validation amendment

_Frozen corrective study; Experiment 002 historical artifacts remain unchanged_

> **Evidence boundary:** This amendment validates the sampled-data methodology
> and frozen PD controller at the existing 1.0 s command/observation setting in
> the six-stratum synthetic generator. It is not flight-safety evidence, a
> multi-rate qualification, or a confirmatory architecture claim.

## Decision

**`fail`**. The full 32,000-episode confirmatory campaign was
not run. The combined-fault nuisance/information study was not run.

## Operational 1.0 s validation

| Stratum | Episodes | Hazards | Successes | Minimum final propellant | 95% upper |
| --- | ---: | ---: | ---: | ---: | ---: |
| P0_nominal | 150 | 0 | 116 | 0.707060 | 0.01977 |
| P1_primary_navigation | 150 | 0 | 51 | 0.671938 | 0.01977 |
| P2_monitor_only | 150 | 0 | 66 | 0.506304 | 0.01977 |
| P3_shared_cause_navigation | 150 | 0 | 61 | 0.623423 | 0.01977 |
| P4_model_upset | 150 | 0 | 150 | 0.424545 | 0.01977 |
| P5_actuator_degradation | 150 | 0 | 120 | 0.711703 | 0.01977 |

The frozen sample was 150 disjoint seeds per stratum. With zero events, the
per-stratum one-sided exact 95% upper bound is
`0.01977`, below the prospective
`0.02` margin. Success is descriptive and need not remain identical across
different sampled-data systems.

## Full fixed-command numerical replay

- Complete traces: 24
- Maximum state or metric error: `7.446e-07`
- Required classifications identical: `true`
- Gate tolerance: `1e-10`

## Rate decomposition

| Command (s) | Observation (s) | Hazards | Successes | Hazard change | Success change | Mean fuel change |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 1 | 0 | 42 | +0.0000 | +0.0000 | +0.00000 |
| 1 | 0.5 | 0 | 42 | +0.0000 | +0.0000 | +0.00000 |
| 1 | 0.25 | 0 | 42 | +0.0000 | +0.0000 | +0.00000 |
| 0.5 | 1 | 0 | 42 | +0.0000 | +0.0000 | -0.00002 |
| 0.5 | 0.5 | 0 | 43 | +0.0000 | +0.0139 | -0.02871 |
| 0.5 | 0.25 | 0 | 43 | +0.0000 | +0.0139 | -0.02871 |
| 0.25 | 1 | 0 | 42 | +0.0000 | +0.0000 | +0.00008 |
| 0.25 | 0.5 | 0 | 43 | +0.0000 | +0.0139 | -0.02873 |
| 0.25 | 0.25 | 0 | 43 | +0.0000 | +0.0139 | -0.04818 |

The 3×3 grid independently varies command hold/update timing and sensor sampling
timing. It is a 12-seed-per-stratum mechanism-identification feasibility design.
Machine-readable evidence retains commands, gate reasons, packet identities, and
fault-response timing. Trajectory, range/fuel, and success identity are not gates
across closed-loop timing configurations. No support is claimed for 0.5 s or
0.25 s command periods.

## Next step

`investigate_experiment_002b_failure`. The confirmatory campaign remains blocked until its
separate combined-fault nuisance/information requirement is prospectively resolved.
