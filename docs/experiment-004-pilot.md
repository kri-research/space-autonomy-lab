# Experiment 004 planar HCW design-validation pilot

Experiment 004 extends the research harness to planar Hill–Clohessy–Wiltshire relative motion. The
foundation is frozen separately in [`experiments/004/`](../experiments/004/). This additive directory
contains only the design for a future non-inferential engineering pilot.

## What the pilot will validate

The pilot is intended to show that the exact HCW propagator, continuous-arc geometry evaluator,
mission dwell evaluator, primary and monitor navigation filters, channel-bounded faults, shared-cause
faults, vector actuation path, deterministic LQR, estimated-geometry monitor, complete-block runner,
and deterministic replay all activate as specified.

The matrix deliberately separates:

- physical geometry fixtures: collision, keep-out entry without collision, and corridor departure;
- nominal mission feasibility;
- primary navigation bias and dropout;
- monitor navigation bias and monitor-logic false trip;
- shared-channel navigation bias;
- actuation effectiveness loss and additive disturbance.

The exact matrix is [`case-matrix.json`](../experiments/004-pilot/case-matrix.json). Four roots per
case and two diagnostic configurations produce 44 complete blocks and 88 future episodes. The
outcome-blind replay subset contains 11 blocks and 22 episodes.

## Interpretation boundary

This is not an architecture comparison and does not test a scientific hypothesis. Results may only
be summarized as prespecified gate activation, completeness, numerical validity, channel routing,
and replay identity. No p-values, superiority or noninferiority claims, architecture ranking,
confirmatory inference, operational-frequency claim, or flight-safety conclusion is permitted.

The plant is a local planar linear circular-orbit model. It excludes nonlinear orbital mechanics,
three-dimensional translation, attitude dynamics, plume and contact dynamics, timing jitter beyond
the frozen packet model, flight software, hardware-in-the-loop, and operational validation.

## Partition states

- Partition 41: used only for recorded prospective mechanics calibration.
- Partition 42: reserved and unused; the reference controller is deterministic and not fitted.
- Partition 43: reserved for one future write-once pilot seed materialization and execution.
- Partition 44: reserved and unmaterialized, with no hypothesis, sample size, or generator.
- Partition 941: deterministic unit-test fixtures only.

The next task after a successful design freeze is exactly one non-inferential Experiment 004
partition-43 design-validation pilot execution. Confirmatory design, six-degree-of-freedom work,
hardware-in-the-loop work, and manuscript preparation remain out of scope.
