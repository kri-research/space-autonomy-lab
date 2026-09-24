# Measured host execution and external-validation preparation

This additive package measures real host-computer execution and prepares physical
and independent review work. It does not provide a physical actuator driver.
The supplied computer is the available host; no dedicated target processor,
independent metrology or supervised research rig was verified for this study.
A listed serial endpoint is not evidence of a suitable connected robot.

## Evidence levels

| Evidence level | Achieved state | Boundary |
|---|---|---|
| Host-computer timing | Measured | One host, correlated process sessions |
| Simulated interface | Tested | No physical I/O |
| Processor-in-the-loop | Not performed | No dedicated target processor/interface |
| Hardware-in-the-loop | Not performed | No real sensor/actuator path |
| Physical-system trials | Not performed | Rig, metrology, supervision and approval missing |
| Independent external replication | Not performed | No reviewer or laboratory report received |


The host study uses three fresh interpreter/service sessions on one computer,
with two retained warm-up calls per adapter and two repetitions of eight exposed
calibration inputs. All 192 measured and 24 warm-up requests are predeclared.
Three lagged-cart methods share the same inputs, device, one-second budget and
finite-prefix obligation. The spacecraft common-command implementation is also
measured, but is not pooled with the cart methods for controller ranking.
The same reference models and existing scalar/spacecraft limitations remain.

No protected spacecraft or transfer trial is rerun. Repeated calibration calls
are labeled host measurements; they add no independent protected population.
Only the host clock is measured. Sensor acquisition, network transfer to physical
equipment, independent clock alignment and actuator response are not measured.
A new source freeze binds these timing trials without modifying earlier freezes.

## Measurement interface and clocks

The JSON line service binds version, sequence, request identity, SI units, input
identity, model and method. It returns the original mathematical result and
an explicit finite-held-command scope. The transport records parent serialization,
send, return and validation times plus worker policy/service and process CPU times.
The hot call excludes interpreter startup and imports, which are recorded separately.
All timings are actual perf_counter_ns/process_time_ns samples. Absolute clock
origins are removed; intervals retain the original integer nanoseconds.

Cold session starts, two warm-ups, method order, host load and power-source snapshots
are retained. Cache behavior follows the unchanged implementations. No samples
are discarded as outliers. Reciprocal mean roundtrip is a synchronous service-rate
proxy excluding inter-request logging, not an achieved sustained control-loop rate.
Advertised clock resolution and back-to-back readings do not calibrate frequency,
drift or absolute accuracy. One computer/day with three process sessions does not
establish independent-hardware variation or worst-case execution time.

The one-second policy admission budget differs from the physical application time.
Compare measured whole-service duration to the input's actual queued duration D.
If the host duration alone exceeds D, a literal implementation of that timing
pattern cannot use this request path. Otherwise physical timing remains unknown
without sensor, actuation and clock-alignment bounds. Do not silently add a delay
to a proved trajectory. An early reply must wait until the modeled application
instant with the known queue preserved. Late, duplicate, unverified or stopped
requests are rejected by the virtual sink; it has a latched simulated stop.

## Reproduction and external work

From the study root, run `python -m pytest execution_validation_v1/tests` for
synthetic and exposed-calibration interface checks only. A new host experiment
requires a committed-source host freeze and a new private output directory.
The recorded artifact verifier and LaTeX bridge perform read-only checks.
Do not reuse host timing as a physical or independent-review result.

LAB_PROTOCOL.md gives the bounded trial, metrology, clock, reset and abort process.
The placeholder configuration deliberately fails readiness. Any future real trial
needs actual identified hardware, a human operator, independent safety supervisor,
traceable metrology and separate trial-specific permission. No tool in this package
opens serial ports, cameras or networked robots. The metrology checker consumes
external data only and cannot authenticate its origin or authorize motion.

REVIEW_QUESTIONS.md asks concrete GNC and numerical/statistical questions.
The bundle builder creates a compact local standard-library numerical referee
package without publishing the manuscript or inviting reviewers. External reports
must be genuinely received, attributed and addressed before review is claimed.
