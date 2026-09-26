# SA04 deadline-aware execution contract

## Represented system

This additive adapter keeps the SA01 HCW model, SI frame, standoff geometry,
0.02 m/s2 Euclidean authority, effectiveness [0.8,1] and component disturbance
1e-5 m/s2. It imports SA02 observation construction and both SA03 policies unchanged.
The 27 reused source identities, including the original execution protocol, are
in source-map.json. Existing protocols, timings and scientific results are preserved.

The planner's full sensing tree is now an untrusted proposal menu. A smaller trusted
checker reconstructs SA02 uncertainty from actually received packets and checks the
proposed action. It does not trust planner state boxes, hashes or success flags as
mathematical evidence. This removes complete outcome enumeration from the checking
path, but does not establish a faster worst case or independent numerical checking.
SA03 all-reading usefulness is not claimed as this adapter's runtime result.

## Time and the new application window

The snapshot remains 100 ms; the complete planning response is due by 150 ms.
A permitted simulated request selects acquisition at 250 ms. Complete received
history is checked from a 650 ms snapshot; response, validation, logging and admission
must finish by 700 ms. Slow computation does not extend these deadlines.

A general host cannot promise an exact mathematical dispatch instant. SA04 therefore
introduces a separately verified initiation window [700,710] ms, while terminating
the input at the original 1200 ms and coasting to 4200 ms. Hold duration is 490 to
500 ms. No previous exact-700-ms result is relabelled as jitter-robust; no observation
or computation budget is lengthened to fit observed cost.

The new checker propagates the reconstructed set through the known queue, zero
waiting, the initiation band, the remaining input and the three-second coast.
During [700,710] it encloses effectiveness in [0,1], covering zero before the switch
and an allowed effective command afterwards. After 710 ms it uses [0.8,1]. This
inclusion covers every allowed switch instant; losing correlation only enlarges it.
The unchanged rational Picard/Euler method checks continuous tubes, splitting at all
schedule boundaries with steps <=50 ms. Each tube must be inside the closed research
box and outside the closed 10 m exclusion circle. Failures are unresolved, never
physical impossibility. A separate rational HCW point oracle corroborates small
initiation-band cases; it is not a full second checker.

There is no terminal-invariance, full-recovery or convergence theorem. Exact shutdown
at 1200 ms is still an assumed preloaded low-level scheduler behavior. The 10 ms
allowance covers initiation only, not arbitrary actuator lag, clock drift or delayed
termination. Physical implementation needs those bounds and a validated scheduler.

## Finite fallback and initialization

Before a future simulated episode, the supplied initial domain and queued-then-zero
continuation are checked to 4200 ms. Only an admitted domain arms protection. Worker
startup and this offline preparation are separately measured; they do not freeze a
live vehicle while software starts. The future simulated initial state must belong
to the checked domain. No valid coast means no credited operation.

An invalid, missing or late candidate leaves only the already checked finite
continuation, conditional on its own initial/dynamics assumptions. At 4200 ms credit
ends. Known queue, model, actuator or clock invalidation removes affected credit.
A missing acknowledgement is not evidence of actuation success. Zero output after
invalidation is explicitly uncredited. A stopped Python parent is not claimed to
leave real hardware safe: the autonomous fallback scheduler exists only in simulation.

## Binding and trust

Messages carry role, version, session, monotone sequence, canonical payload identity
and complete model configuration. Bounded framing rejects excessive length, depth,
collections, numeric spelling, nonfinite values, duplicate keys and truncated frames.
Original strict_load, check_action and delay_compatibility functions are reused via a
pinned adapter. Physical latency remains unknown when its bounds are absent.

Checks bind initial domain, packet identities, acquisition/availability times, clock
assumptions, sensor/fault contract, applied history, queued input, reconstructed set,
proposed action, start window, command end and expiry. The gate compares the armed
initial contract, snapshots accepted results, rejects repeats and requires the same
live-context fingerprint at dispatch. A changed situation requires a fresh check.
The caller supplying that live fingerprint and input acquisition are trusted components.

The trusted base includes SA02 inference, rational arithmetic/flow, configuration and
receipt acquisition, checker worker, transport client, gate and OS. Role-separated
processes support failure/timeout containment, not independent mathematics. Checksums
are not authentication against replacement of the trusted checker or fabricated sensor
truth. There is no network listener or physical actuator driver. Sensor error bounds
are assumed; an undetected out-of-model bias can still invalidate a nonempty estimate.

## Trace and host evidence

Versioned events retain inputs, proposals, requests, observations, uncertainty/check
results, admission, command signal, simulated acknowledgement, evaluation-only
consequence and post-expiry end. A read-only replay reconstructs arming and checking,
then checks causal ordering and gate state. It detects stale input, outdated proofs,
wrong command timing and an unchanged fallback mislabeled as intervention, including
coedited trace hashes. It shares mathematical routines; it is not external replication.

The engineering fixtures have explicit simulated phase durations. The host experiment
is separate. Its diagnostic mode measures the full path without dispatch authority.
Its enforced mode uses parent monotonic time, nonblocking pipe timeouts, owned-child
cancellation and absolute admission/dispatch limits. Completion of the admission check itself
is included in its deadline; a pre-deadline check start is insufficient. Only a virtual signal wholly
inside the initiation window receives a timed-emission label. Parent and child clock
origins are never subtracted. All sensor timestamps and physical delays remain assumed.

The prospective host protocol specifies three process sessions, two warmups per session,
two repetitions of three contexts and two methods (36 diagnostic calls), plus twelve
fresh deadline-enforced trials. Every sample and timeout is retained. Startup, load,
uncertainty update, planning, checking, serialization, IPC, validation, logging,
scheduling and signal copying are measured in their identified scopes. Read timeouts
record cancellation separately. Logging is write/flush, not durable fsync. Peak RSS
is a process high-water mark rather than per-call allocation. Samples are correlated
observations from one host; measured maxima are not WCET proofs.

No CPU time, memory, clock rate or advertised power becomes measured energy savings.
Target timing, real sensor/actuator latency, cross-device alignment, energy and external
validation remain unperformed. SA05 can evaluate the software under explicit simulated
resource/timing assumptions, retaining actual overruns and the restricted entry domain.
