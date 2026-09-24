# Bounded physical validation protocol

Status: preparation only. No physical trial is authorized or frozen. The shipped
package has no driver capable of moving equipment. Its virtual sink cannot be
connected to an actuator by a configuration switch.

## Required rig and responsible people

A supervised planar test rig is required with measured cart mass, actuator lag,
force saturation, actuator-state sensing and a separately recorded center-position
reference. The previous 2 kg, 0.8 N and lag values are synthetic and must never be
entered as measurements. A safety supervisor separate from the experimental
controller must have a tested hard emergency stop and a restricted workspace.
The operator and supervisor must be named in a private approval record, along
with trial-specific user authorization. No camera/serial device discovered on a
computer is automatically a suitable or authorized rig.

An external position system must be independent of the controller observations.
Record instrument serial/calibration details privately, plus public instrument
model, calibration method, uncertainty, sample rate and bounded clock alignment.
Velocity and actuator-state uncertainty must be established as well. Compare the
measured bounds with the modeled information boxes; the original 1 mm, 1 mm/s and
2 mm/s2 halfwidths are not presumed achievable. Broaden a new model before its
freeze when necessary; never rewrite the previous transfer test.

## Identification and freeze

First perform a separately authorized low-energy identification session, or use
traceable existing calibration data. Identify lag, effectiveness, saturation,
state/measurement uncertainty and residual disturbance over the proposed domain.
The current cart proof assumes a known lag and effectiveness and a constant
unknown disturbance. Real time-varying model error cannot silently be described
as a constant disturbance. Where these assumptions are not supportable, restrict
the physical result to prediction-versus-observation and report the mismatch;
claiming robust physical containment would require a separately validated model.

Before any validation outcomes, a human-approved manifest must bind source and
adapter firmware, actual physical parameters and uncertainty, exact initial-state
list, reset tolerances, block order, endpoints, session count, stopping rules,
metrology processing and discrepancy analysis. Complete physical_configuration.json
and retain the approval artifacts. The readiness checker checks completeness only,
not authenticity or safety authorization. A physical experiment needs a new
identifier; the host timing freeze is not a physical-trial freeze.

## Initial states and schedule

Prepare at least three separately reset sessions with temperature, battery/voltage,
processor load, payload and calibration drift recorded at start and end. Treat
these as clustered sessions, not independent samples from a universal population.
Use matched blocks of the lag-aware, robust predictive-prefix and third-order
barrier methods with the same available information and measured input bounds.
Counterbalance method order. Independent resets cannot reproduce identical noise.
Keep each no-new-observation held interval at the frozen duration; the measured
observation age and queued inputs must be represented exactly.

The admissible initial-state set must lie inside the measured workspace with
metrology, controller uncertainty and externally justified stopping margins.
Outward velocity/acceleration, position and power limits must be numerically
filled from rig identification, not from a fictional cart. Cases with an
obstruction or unresolved controller decision are shadow-mode observations only;
never execute an invented zero-input fallback as a safe action. Contact-risk
boundary counterexamples are restricted to simulation or shadow execution.

## Timestamps and emergency handling

Log capture time, packet receipt, compute start/end, command dispatch, actuator
acknowledgment and independently detected physical response with clock domains
and alignment intervals. Include transport and scheduling in the application-time
budget. Early replies wait to the modeled application instant; late replies are
withheld. An unmodeled extra delay changes the physical trajectory assumptions.
The safety supervisor governs an abort and actual stopping behavior, which must
be validated independently of the research controller. Physical braking is not
implemented by the virtual sink.

Stop on metrology loss, clock-bound violation, unexpected motion, overcurrent,
thermal/voltage alarms, any workspace/velocity limit, operator emergency stop or
loss of the safety supervisor. Preserve every attempted trial and abort, including
external-guard interventions and pre/post intervention commands. Never discard a
guard intervention to improve the safety rate. A reset follows a documented
standstill and human check, with reset time/effort counted separately.

## Data and interpretation

For every attempted block store initial-state uncertainty, actual observation
packets, all proposals and applied commands, raw independent metrology, disturbance
measurements, bound violations, reset/abort reasons and source/clock identities.
The import-only metrology_adjudicate function supports the declared triangular
center-position property with deterministic position/alignment/speed bounds.
It preserves ambiguous intervals and all guard records; sampling alone cannot
prove continuous containment. Record gap and bound assumptions explicitly.

Report predictions versus observed continuous violation evidence, conservative
unresolved counts, intervention frequency, task completion only when separately
defined, control effort and full latency. Report session-level differences and
matched block identities. Agree an uncertainty method before data collection;
no independent-trial binomial interval is automatic. A measured disagreement
refutes only the claim whose model and numerical assumptions actually hold.
No hardware, flight readiness or external endorsement follows from this package.
