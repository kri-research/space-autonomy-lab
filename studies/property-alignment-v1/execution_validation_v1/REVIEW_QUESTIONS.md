# Independent technical review request package

No invitations have been sent and no reviewer endorsement is claimed. A new
assistant session or second code path does not count as either review below.

## Spacecraft and control review

Check the manuscript's interpretation of the closed approach/hold union and its
27 m separation implication against the actual research requirement. Are
collision avoidance, corridor adherence and hold acquisition kept separate?
Challenge the common-policy quantifier and the scope of a finite held command.
Check that an obstruction for aliased hypotheses is not called individual
unrecoverability, and that an available prefix is not called recursive recovery.

Review the timestamp contract. Can the stated zero or finite application delay
include actual sensing, computation and actuation? What verified information
propagation or invariant continuation would a flight controller require?
Check fallback behavior and the distinction between override logs and applied
command changes. Evaluate whether the predictive and barrier comparisons retain
their proper domains and continuation obligations. In the transfer result the
predictive method certified 79 prefixes versus 77 for the new criterion; confirm
that no positive-control advantage is claimed.

## Numerical and statistical review

Independently check the interval Taylor remainder, directed exponential bounds,
Bernstein range evaluation, chord-curvature bound and residual-aware dual sign.
Use a different toolchain or independent derivation where feasible. Challenge
boundary/tangency, uncertain initial conditions, queued action and lag mismatch
fixtures. Reproduce fixed records from the supplied independent-referee bundle.

Check the frozen selection, qualification change and retained invalid first
attempt. Assess the conditional-mean interval's target under fixed reveal order
and correlated host timings; it is not operational risk or independent hardware
reliability. Confirm no post-outcome exclusion, retry or sample-size extension.
Review host sample order, warm-up handling, process startup, full-service latency,
clock resolution versus accuracy and the absence of measured sensor/actuator delays.

## Required review record

Provide reviewer identity/affiliation and relevant expertise, independence and
conflicts, exact commit/document versions, methods personally checked, commands
and outputs, specific objections with severity and proposed falsifying test, and
permission for attribution. Private identity details remain outside the public
repository unless authorized. The response log should link each objection to
actual evidence or an explicit unresolved issue; a blank form is not a review.

The local reproducibility bundle contains frozen cart inputs, recorded commands,
the separate standard-library referee and source hashes. It requires no controller
execution to reproduce numerical checks. The public repository supplies the full
spacecraft study at its pinned commits. Human reviewers must inspect the full
manuscript separately under an explicitly authorized sharing arrangement.
