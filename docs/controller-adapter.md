# External controller adapter

The external controller adapter is a small, deterministic bring-your-own-controller boundary for the
simplified one-dimensional rendezvous/proximity-operations testbed. It is separate from the frozen
Experiment 002 implementations and evidence.

This interface is **not** a full guidance, navigation, and control stack, a simulator of record, a
runtime-assurance system, or flight-safety/certification evidence.

## Minimal controller

Create an importable file such as `my_controller.py`:

```python
from kri_space_autonomy.controller_adapter import (
    ControllerCommand,
    ControllerContext,
    ControllerMetadata,
    ControllerObservation,
    ObservationStatus,
)


class MyController:
    metadata = ControllerMetadata(
        controller_id="my-rpo-controller",
        controller_version="1.0.0",
    )

    def reset(self, context: ControllerContext) -> None:
        self.minimum = context.minimum_acceleration_mps2
        self.maximum = context.maximum_acceleration_mps2

    def command(self, observation: ControllerObservation) -> ControllerCommand:
        if observation.status is ObservationStatus.MISSING:
            return ControllerCommand(self.maximum)

        assert observation.range_m is not None
        assert observation.relative_velocity_mps is not None
        target_velocity = -min(0.30, 0.04 * max(0.0, observation.range_m - 6.5))
        acceleration = 0.8 * (target_velocity - observation.relative_velocity_mps)
        return ControllerCommand(min(self.maximum, max(self.minimum, acceleration)))


controller = MyController()
```

The loader accepts `module.path:attribute`. The attribute may be an instance, as above, or a class
with a zero-argument constructor. Users do not edit package or simulator source.

## Validate, run, and replay

From the repository root:

```bash
uv run python -m kri_space_autonomy.controller_adapter \
  validate my_controller:controller

uv run python -m kri_space_autonomy.controller_adapter \
  run my_controller:controller scenarios/nominal.json

uv run python -m kri_space_autonomy.controller_adapter \
  replay my_controller:controller scenarios/nominal.json

# The same import spec through the frozen-estimator product bridge.
uv run python -m kri_space_autonomy.controller_adapter \
  replay my_controller:controller scenarios/nominal.json \
  --navigation-profile estimated
```

The checked-in example can be exercised directly:

```bash
uv run python -m kri_space_autonomy.controller_adapter \
  validate kri_space_autonomy.examples.proportional_controller:controller
```

The same facade is available from Python:

```python
from kri_space_autonomy.controller_adapter import (
    run_external_controller,
    validate_controller,
)

validate_controller("my_controller:controller")
result = run_external_controller("my_controller:controller", "scenarios/nominal.json")
print(result.to_dict())
```

## Contract

### Lifecycle

- The runner constructs or loads one controller, then calls `reset(context)` exactly once before the
  first command of an episode.
- `reset` must clear all episode-local state and return `None`. The same instance can be reset for a
  replay.
- `command(observation)` is called once per command step, beginning at step 0. Steps are contiguous,
  and `time_s == step * context.command_period_s`.
- The controller declares `deterministic=True`. Validation runs nominal, degraded, and missing-input
  probes twice around `reset` and requires exact command replay.
- `ControllerContext` contains only command period, acceleration bounds, acceleration unit, and sign
  convention. Scenario identifiers, fault labels, run arms, and evaluator metadata are not provided.

The deterministic identity record includes `plugin_module_sha256`, the SHA-256 of the exact source
text for the module named in the import spec. It is deliberately not described as a dependency or
artifact manifest: imported modules and external files are outside that digest in this milestone.

### Observable inputs only

`ControllerObservation` contains exactly:

- `step` and `time_s`;
- observed `range_m` and `relative_velocity_mps`, each optionally `None`;
- observed `propellant_fraction` in `[0, 1]`;
- `sensor_quality` in `[0, 1]`.

`observation.status` is derived as `nominal`, `degraded`, or `missing`; `missing_fields` identifies
unavailable navigation fields. Missing values are never filled from simulator truth. Internal state,
achieved actuation, fault state, evaluator state, and monitor state are not passed through the
contract. The optional estimated navigation profile does not change these fields; it maps the frozen
Experiment 003 primary-filter estimate and coarse health into the same contract. Exact mapping,
identity, and model-boundary semantics are documented in
[`navigation-profiles.md`](navigation-profiles.md).

Python plugins run in-process and are trusted local code. The adapter controls its arguments but is
not a process sandbox.

### Command

`ControllerCommand.acceleration_mps2` is relative acceleration, and its `acceleration_unit` must be
`m/s²` (the constructor supplies that default). Positive acceleration increases separation. The
episode context declares inclusive minimum and maximum bounds (the default benchmark uses
`[-0.05, 0.05] m/s²`). The adapter does not clip or reinterpret output.

The adapter stops the episode and raises a typed error for import/construction failures, malformed
metadata, a missing lifecycle method, reset or command exceptions, wrong return types or shapes,
non-real values, `NaN`/`Inf`, out-of-bounds acceleration, wrong step/time sequencing, or non-replayable
validation output. Raw scalars and mappings are rejected so a value with unstated units cannot cross
the boundary accidentally.

## Current scope

The facade reuses the simplified deterministic environment and supports nominal, sensor bias, sensor
dropout, and actuator-degradation scenario behavior. `direct` remains the default; `estimated`
imports and verifies the frozen Experiment 003 estimator without retuning it. The existing
`model-seu` scenario targets the built-in learned-policy representation and is rejected for external
controllers. Generic controller fault injection, an independent product monitor, richer dynamics,
and timeouts/process isolation remain out of scope.
