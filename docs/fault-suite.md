# Deterministic external-controller fault suites

The fault-suite facade exercises an importable controller through the existing public controller
adapter. It is a simplified one-dimensional rendezvous/proximity-operations (RPO) controller test
harness. It is not a complete guidance, navigation, and control stack, a simulator of record, a
flight-safety or certification system, or an assurance report.

The facade is separate from the frozen Experiment 002 family and does not modify its code, inputs,
or evidence.

## Minimal suite

Suites use strict JSON. All keys shown below are required, including descriptions and units. Fault
activation windows are inclusive at both `start_step` and `end_step`.

```json
{
  "schema_version": "kri-fault-suite/1.0",
  "suite_id": "my-rpo-suite",
  "description": "Nominal and one observed-range fault.",
  "runtime_profile": "simplified-rpo-v1",
  "initial_state": {
    "range": {"value": 100.0, "unit": "m"},
    "relative_velocity": {"value": -0.15, "unit": "m/s"},
    "propellant_fraction": {"value": 1.0, "unit": "ratio"}
  },
  "cases": [
    {
      "id": "nominal",
      "description": "No injected fault.",
      "faults": []
    },
    {
      "id": "biased-range",
      "description": "Range is biased high for eleven command steps.",
      "faults": [
        {
          "id": "primary-range-bias",
          "type": "observed_range_bias",
          "activation": {"start_step": 250, "end_step": 260},
          "bias": {"value": 20.0, "unit": "m"},
          "sensor_quality": {"value": 0.8, "unit": "ratio"}
        }
      ]
    }
  ]
}
```

The checked-in example at [`fault-suites/example-rpo.json`](../fault-suites/example-rpo.json)
contains nominal, each built-in fault, and a composed case.

`simplified-rpo-v1` fixes a 1 s command period, 500-step limit, ±0.05 m/s² command bounds,
1 m collision range, 5–8 m goal range, 0.06 m/s goal-speed limit, and the existing deterministic
one-dimensional environment/propellant semantics. A semantic change requires a new profile name.
Cases execute in manifest-array order from the same declared initial state.

## Validate, run, and replay

From the repository root:

```bash
uv run python -m kri_space_autonomy.fault_suite \
  validate fault-suites/example-rpo.json

uv run python -m kri_space_autonomy.fault_suite \
  run-suite kri_space_autonomy.examples.proportional_controller:controller \
  fault-suites/example-rpo.json --output fault-suite-result.json

uv run python -m kri_space_autonomy.fault_suite \
  replay-suite kri_space_autonomy.examples.proportional_controller:controller \
  fault-suites/example-rpo.json
```

The same facade is available from Python:

```python
from kri_space_autonomy.fault_suite import (
    load_fault_suite,
    replay_fault_suite,
    run_fault_suite,
    validate_fault_suite,
)

suite = load_fault_suite("fault-suites/example-rpo.json")
validation = validate_fault_suite("fault-suites/example-rpo.json")
result = run_fault_suite("my_controller:controller", suite)
replay = replay_fault_suite("my_controller:controller", suite)
```

`validate_fault_suite` rejects duplicate JSON keys, non-finite values, booleans used as numbers,
unknown keys, wrong units, invalid identifiers, out-of-range values, reversed or out-of-profile
activation windows, duplicate case/fault IDs, and unsupported fault types. Failures use typed
`FaultSuiteError` subclasses. The canonical SHA-256 identity is computed from normalized,
project-relative data; file formatting and the local source path are not part of the identity.
Changing fault array order changes case and suite identity.

## Supported faults and composition

Faults are applied in each case's JSON-array order. All current built-ins are deterministic and may
be combined:

- `observed_range_bias`: adds the declared metre bias to the currently observed range and lowers
  sensor quality to the minimum quality reached so far. It does nothing to an already-missing range.
- `navigation_dropout`: makes observed range and relative velocity unavailable and sets sensor
  quality to zero. Missing values are not replaced with simulator truth.
- `actuator_effectiveness`: multiplies the requested acceleration after the controller returns its
  command and before the environment step. Overlapping effectiveness faults multiply in array order.

Observation faults run in array order before `command(observation)`. Actuator faults run in the same
array order after the command. The controller still receives exactly one `ControllerObservation`
under controller contract 1.0; no fault schedule, achieved actuation, simulator state, evaluator
state, or case metadata is added to its arguments.

## Output and trust boundary

`run-suite` emits `kri-fault-suite-result/1.0` JSON containing suite, case, controller-module, command
trace, and complete-result hashes plus bounded per-case outcomes. Final range, speed, collision,
success, and propellant are post-run evaluator outputs. They are not passed back to the controller.
Raw simulator-state traces and polished assurance scoring are deliberately out of scope.

Controllers are local in-process plugins. The adapter limits the arguments it supplies, but it is not
a process sandbox; only trusted controller code should be loaded.

## Unsupported classes

Generic controller-internal or learned-representation corruption is unsupported in this milestone.
The stable external-controller contract has no controller-independent way to express or verify such a
change. Reserved internal-upset types fail closed with `UnsupportedFaultError`; they are not replaced
with a misleading observation or actuator fault. A later contract version may add an explicit,
controller-declared capability with controller-specific validation.

The [assessment report layer](assurance-report.md) consumes these deterministic results to produce
stable JSON and concise Markdown against an explicit user-declared policy, without changing suite
execution semantics.
