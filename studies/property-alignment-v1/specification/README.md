# Physical property and executable semantics

This specification continues the existing research. It is a prospective research contract, not a flight requirement, a frozen evaluation population, a new controller, or a certificate of spacecraft recoverability. Historical source, records and decisions remain unchanged.

## Requirement authority

The numerical geometry is a benchmark choice inherited from `experiments/004/preregistration.md` and `experiments/005/preregistration.md` at commit `5539de5753092b09fd78351095292e7627047794`. E005 explicitly acknowledges the E004 out-of-band behavior, retains that online implementation, and defines the closed union for its offline evaluator. The mismatch was therefore acknowledged before the present reanalysis. Its experimental consequences remain testable; discovering the discrepancy for the first time is not a contribution claimed here.

NASA/TM-2011-217088, PDF page 17, describes an Orbital Express abort through a preplanned separation corridor toward a separate trailing safe-hold region [NASA11 in related_work.json]. This supports mission-specific abort definitions. It supplies no requirement for this benchmark's dimensions, no endorsement of its controller, and no justification for calling every union violation an operational hazard.

## Contract

`property_contract.json` fixes the planar radial-outward/prograde LVLH coordinates, SI units, approach corridor A, hold ellipse H and S=A union H. `contract.py` loads the numerical fields and rejects unsupported units or coordinate order. Its point classifier returns separate union, collision, keep-out and hold-eligibility fields. It never assigns spacecraft recoverability from position membership. Nonplanar states require a different explicit interface; six-component vectors are not silently projected.

S is required for all of [0,300 s], including the initial point, in approach, holding and abort-labelled operation. Entering H does not itself change the position constraint to H. The speed bound 0.05 m/s applies to qualifying hold intervals, not every approach state. Hold acquisition requires one continuous 60 s interval; later holding cannot erase an earlier exclusion. An abort request does not terminate outcome accounting, authorize departure from S or count as nominal completion. A mission-authorized retreat outside S would require a separately specified endpoint and corridor before evaluation.

`IntervalEvidence` is an interface for independent interval adjudication, to be implemented and validated separately. Physical verdicts are satisfied, violated or unresolved. Hold coverage is all-eligible, none-eligible or unresolved; a mixed interval is unresolved, not none-eligible. The reducer computes lower and upper possible dwell durations, rejects sample-only evidence and incomplete time coverage, and preserves unresolved outcomes. Its conclusions are conditional on supplied interval evidence. No metadata label alone establishes numerical soundness.

## Information and control

`Information.estimate` and componentwise deterministic error bounds refer to `measured_at`; receipt, decision and application are distinct times. Covariance-only information cannot be converted into deterministic bounds. The timing method computes age and delay but produces no current-state enclosure. A filter estimate already propagated to the decision time must not have its age applied twice.

`validate_pending_commands` requires a complete explicit held-command history through the intended application time. Missing inputs are not silently set to zero. A future enclosure must propagate these inputs and their actual uncertainty. `ExecutionBounds` requires finite, explicit effectiveness, disturbance and timing bounds; none is inferred from historical Gaussian standard deviations. Values for future challenge sweeps remain unset.

Commands obey a 0.02 m/s^2 Euclidean bound and are held in local components. Realized acceleration is effectiveness times the delayed held command plus disturbance and need not obey the command bound. Mapping to inertial coordinates rotates with the chief. The historical same-LQR fallback and unavailable-state zero command have no invariant backup proof. A future recovery method must supply one under its stated assumptions.

## Evidence distinctions

Initially outside S, inside S with unassessed recoverability, proved state-unrecoverable, proved absence of a common information-compatible policy, and certified common-policy recovery are different classifications. Only the scalar analytical fixtures below establish recovery classifications in this task. The spacecraft classification remains unassessed. All 534 initially outside E004 primary roots remain in their original population.

The two exact rational examples in `analytical.py` and `fixtures.py` illustrate known braking and information-pattern reasoning. They are not orbital simulations, prevalence estimates, or new theorems. `research_question.md` states the narrower candidate contribution and its falsifiers; `related_work.json` records source identities and actual access limits.

## Reproduce the specification checks

From the `studies/property-alignment-v1` directory, using the existing pinned study environment and `SAL_EVIDENCE_ROOT` pointing to the separate historical checkout:

```sh
python -m pytest tests
python -m specification.fixtures
```

The first command includes contract, analytical and artifact-exchange tests. The second prints the exact analytical results; `--output path.json` writes a separate copy. The checked-in `analytical_fixtures.json` is generated by that module and tested against its exact execution. Neither command runs a new spacecraft campaign, tunes a method or consumes held-out transfer outcomes.
