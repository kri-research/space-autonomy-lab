# Experiment 004: planar HCW pre-outcome foundation

## Status

This milestone establishes a planar two-axis orbital relative-motion foundation. It contains no
Experiment 004 pilot or confirmatory outcome campaign and makes no scientific outcome claim.

Historical context remains unchanged. The final Experiment 002 direct-measurement campaign was
favorable under its frozen synthetic design. The final Experiment 003 estimator-in-loop campaign
was valid and reproducible but inconclusive: D and PD had no `analysis_hazard` events in any E0-E6
stratum, H1 PD-D was 0 with a 95% interval of `[0, 0]`, H2 was gate-closed, and descriptive PD-D
sustained success was -0.184 overall, with the largest degradation in E5/E6.

## Fidelity step

The new research package uses the planar state

```text
[x_radial_m, y_alongtrack_m, vx_radial_mps, vy_alongtrack_mps]
```

and commanded LVLH acceleration

```text
[ax_radial_mps2, ay_alongtrack_mps2].
```

The target-centered LVLH convention is `+x` radial outward and `+y` along-track. The circular Earth
reference has `mu = 3.986004418e14 m^3/s^2`, radius `6,778,137 m`, and mean motion
`0.0011313666536110223 rad/s`. Exact zero-order-hold HCW propagation uses an augmented matrix
exponential and is checked against independent analytical matrices and scalar DOP853 integration.
This is a local circular-orbit linear approximation, not nonlinear orbital mechanics.

The benchmark geometry is a trailing V-bar approach from near `(0, -100) m` to an exterior hold at
`(0, -30) m`. It has a closed 2 m center-to-center collision disk, a closed 10 m keep-out disk, a
tapered approach corridor, and an elliptical position-plus-speed hold region. Events are evaluated
on exact one-second-or-shorter HCW arcs, not endpoint chords.

## Navigation, control and evidence boundaries

A four-state fixed-lag linear filter consumes timestamped Cartesian position/velocity packets and
4 by 4 covariance matrices with explicit mixed units. Prediction, Joseph-form update, innovation
rejection, covariance checks, integer-tick replay and fail-closed divergence behavior are isolated
from physical state and fault labels. Primary and monitor channels remain separate.

An additive vector research contract supports a deterministic bounded LQR hold reference and a
bounded estimated-geometry monitor. The stable scalar product interfaces and defaults are not
changed. The reference controller is not fitted and no learned policy is trained in this
milestone.

The independent evaluator keeps physical geometry, mission performance, primary-estimator faults,
monitor faults, shared-cause faults and other technical failures separate. No aggregate primary
hazard endpoint or future inferential arm family is frozen.

## Prospective partitions

Master seed 4004 reserves independent domains for dynamics/metric calibration (41), future fitting
(42), design-validation pilot work (43), future confirmatory work (44), and deterministic fixtures
(941). No partition 41-44 seed manifest or result directory exists. Partition 44 has no hypothesis,
sample size, or generator.

## Validation boundary

Foundation readiness is based on numerical/reference agreement, exact-arc event fixtures,
observability, covariance integrity, fixed-lag equivalence, deterministic replay, interface leakage
checks, partition absence/disjointness, locked runtime identity, historical campaign verification,
byte identity of the merged base tree, repository tests, and publication/privacy checks. The
600-second deterministic trajectory is a feasibility fixture only.

## Next task

Freeze one separate non-inferential design-validation pilot matrix and sample count using only
partition-41 calibration. The pilot must exercise nominal, forced-event, channel-specific,
shared-channel and actuation cases; validate event and fault activation, complete blocks and replay;
and only then enable a write-once partition-43 generator. It must not materialize partition 44 or
perform confirmatory inference.

The complete frozen contract is in `experiments/004/preregistration.md`.
