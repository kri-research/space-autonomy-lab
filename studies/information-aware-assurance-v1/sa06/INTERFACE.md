# Public research interface

## Supported purpose

The stable entry points are `api.contract`, `api.make_request`, `api.assess`,
`api.estimate_snapshot`, `api.observation_packet`, `api.record`, `api.replay`, and the file-based CLI.
Version 0.1.0 implements `kri-assurance-assessment/1`. This adapter assesses a
proposed command; it does not issue a physical command, authenticate a remote
certificate, or prove that a supplied sensor assumption is true. No network or
serial driver is included. Callbacks are ordinary trusted Python code, not a sandbox.

The private `_vendor` namespace is not a supported extension surface. It contains
source-pinned KRI implementations with import relocation. The same rational
observer and flow calculations remain in the trusted computing base. An installed
source check detects accidental changed/mixed bytes, not a malicious interpreter
or an attacker able to replace both code and its inventory.

## Inputs

`contract()` supplies the exact version, model, frame, timing and evidence scope.
Every field must match; unknown or changed fields fail rather than selecting an
unverified new model. Inputs use metres, seconds and metre/second state components,
metre/second-squared acceleration, radian bearing, and nonnegative integer
milliseconds from one specified epoch. Rational values may use strings such as
`"1/50"`; booleans are not numeric values. The command norm is at most 0.02 m/s2.

`make_request(initial, current, action, ready_ms=675, apply_ms=700,
assumptions_supported=True)` returns a detached request. `assess` accepts that
request or its JSON equivalent. Fields are:

| Field | Meaning |
| --- | --- |
| contract | Exact `contract()` output, including simulation-only scope. |
| initial_input | Declared prior at epoch zero and complete received/applied history through the 100 ms arming snapshot. |
| current_input | Same initial, sensor, timing and queue assumptions, with complete history and delivered observations to its `at_ms`. |
| proposed_action | Two acceleration components. No supplied safety Boolean or certificate is accepted. |
| ready_ms | Modeled completion of checking/admission, not a measured host duration. It must be at or after the current snapshot and no later than 700 ms. |
| apply_ms | Simulated application time in the verified [700,710] ms start band; later ticks report a missed window/expiry, not a retimed valid action. |
| assumptions_supported | Explicit declared validity. False prevents a protection claim; true does not establish calibration or fault detection. |

Each snapshot has exactly `initial`, `sensors`, `packets`, `history`, `at_ms`,
`queued_action`, `timing`. Initial and sensor fields have the complete schemas
shown in the embedded public examples. Obtain an editable example without
importing implementation internals:

```python
import json
from kri_assurance_eval.examples import examples
from kri_assurance_eval.api import assess, record

request = examples()[0]["request"]
request["proposed_action"] = ["0", "1/50"]
print(assess(request)["status"])
with open("request.json", "x") as f:
    json.dump(request, f)
with open("receipt.json", "x") as f:
    json.dump(record(request), f)
```

The public `observation_packet` helper constructs and validates a packet without
importing private implementation types. The two observation examples represent a
stationary nominal (0,-45,0,0) state under zero pre-action input; they are synthetic
engineering inputs, not real sensor measurements.

Observation packets use `iaa-observation/1` and carry packet identity, sequence,
channel, value, acquisition/availability timestamps, timestamp uncertainty, unit
and frame. Only packets already available at the current snapshot may cross the
assessment boundary. The `sensors` structure describes bounded range/bearing
errors and coherent bias hypotheses, not covariance confidence converted to a
guarantee. State reconstruction occurs inside the checker; another controller
cannot inject an optimistic precomputed state set in place of observations.

History is contiguous from epoch zero to `at_ms`. The input queued from 100 to
200 ms is fixed; the waiting input from 200 to 700 ms is zero. An altered received
packet, initial hypothesis, history prefix, dynamics or queue requires a new
compatible assessment. No previous assessment can be submitted as authority.

## Results and lifetime

| Status | Interpretation |
| --- | --- |
| supported_prefix | Reconstructed observation set and proposed action pass the finite conditional model checks and modeled timing. This is not measured execution, mission completion or recovery. |
| uncredited_entry | Initial zero-input protection is not established; there is no automatic safe fallback. |
| assumptions_unavailable | Caller declares assumptions unsupported; no protection is credited. |
| unresolved | The sufficient checker could not establish the candidate obligation. It does not prove physical impossibility. |
| late | Modeled checking/admission missed 700 ms. No new candidate is credited. |
| rejected_binding | A ready-time or binding condition failed. Inspect the admission reasons. |
| missed_application_window | The candidate was not applied in [700,710] ms. A prior finite coast, if valid, is separate. |
| unsupported_input | A malformed, incompatible, unbounded or changed-source input was rejected. No authority is returned. |

Any candidate ends at 1200 ms, regardless of its permitted start within the band;
the checked coast expires at 4200 ms. Before the current snapshot, protection is
only the separately checked preloaded queue/coast under its entry assumptions.
After expiry there is no credited continuation. A zero candidate is explicitly
not counted as an effective change from coasting. Numeric results may be useful
for design diagnostics; they are not a flight permission or KRI conformance test.

`estimate_snapshot` returns an outer set and its observation status. Missing/stale,
inconsistent, unsupported-packet, resource-exhausted and numerical/history-failure
states retain the original SA02 semantics. An inconsistent empty output means
incompatible data/assumptions; a nonempty set can still exclude truth under an
undetected assumption violation. The returned corners are not attainable negative
witnesses. All assumed sensors/dynamics and finite horizons remain explicit.

## Replay and resource boundary

`record` stores the exact request and recomputed result. `replay` checks the
content identity and independently invokes the same implementation again; it is
internal semantic reproduction, not independent mathematics or authenticated
custody. There are no persistent live command slots in this stateless interface.
Two separate assessment calls are not two authorized physical executions.

Wire input is capped at 262144 bytes, bounded depth/collection/string/numeric
sizes, 128 packets and 256 history segments. Worker operation limits remain the
inherited limits. The API is synchronous and may exceed a spacecraft deadline;
the explicit SA04 process/watchdog evidence remains separate. The wrapper adds
integrity/serialization work and does not inherit any old timing value as its own.
The benchmark measures its whole synchronous assessment call plus process CPU
and memory high-water marks. Startup, physical sensing, communication, actuation,
clock alignment and electrical energy are not measured by that benchmark.
