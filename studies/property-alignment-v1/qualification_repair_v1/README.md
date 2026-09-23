# Qualification runtime repair

## Scope

This additive Task 08B module repairs the pre-candidate qualification bottleneck diagnosed in `runtime_diagnosis_v1`. The frozen `evaluation`, `candidate`, `adjudication`, `protective` and historical evidence files are unchanged. This module does not restart the invalid campaign, generate fresh protected inputs, change the candidate's one-second policy budget, or create a replacement freeze. Integration into a new identified evaluation belongs to Task 08C.

The declared qualification remains a sufficient library-based condition: every compatible hypothesis must admit its immutable queue and a one-second HCW continuation under the original 13 commanded accelerations. It is neither full recoverability nor operational safety. Numerical qualification methods are versioned; global equality of their conservative certification domains is not presumed.

## Repair and argument

Let D be observation age plus application delay, and let Q denote the known command queue on [0,D]. Every future command has exactly the same motion before D. If an attainable initial state and an allowed realized acceleration give an enclosed point outside the physical union or inside a forbidden disk at any t <= D, no later command can meet the full-prefix containment obligation. The code records that particular initial state, disturbance, effectiveness, time and information-set identity. The rechecker reconstructs the point trajectory from the original integration code. This implication uses causality and the given command queue, not optimizer infeasibility or a corner of a propagated overapproximation.

Each full initial hypothesis box is propagated through Q once. Once its entire queue prefix has passed continuous enclosure checks, its exact final numerical box is reused for each subsequent action. The resulting quarter-second continuation arcs equal those from the unmodified full-schedule propagation, as tested directly. Uncertainty, actuator norm bounds, input splitting, physical geometry and outward arithmetic are unchanged.

A point enclosure overlapping a boundary does not establish a violation. It does establish that the current sufficient range-enclosure proof cannot certify that point: the inclusion-isotonic interval extension for any time interval containing it also contains its point enclosure. The checker therefore stops that insufficient search instead of subdividing time thousands of times while the uncertainty width remains. A positive verdict still requires a covering collection of continuous range enclosures, including all intermediate times. Initial/end/midpoint probes alone can never establish containment, and narrow between-probe excursions are tested explicitly. Arithmetic errors and malformed/gapped arcs are separate computation failures.

Only physical prefix containment, collision exclusion and keep-out exclusion are computed here. Hold duration and a minimum-separation estimate are not qualification obligations and are not inferred. The old 1/4096-second minimum cell width and 32,768-cell per-window budget are retained. The search is allowed to abstain; completeness is not claimed. Every accepted development action is also replayed through the original full-schedule adjudicator.

## Result meanings

| Status | Eligibility | Meaning |
| --- | --- | --- |
| `qualified` | true | Every hypothesis has a continuous range proof for the queue and a fixed-library continuation |
| `proved_precommand_violation` | false | A rechecked attainable queue violation precludes the full-prefix obligation |
| `not_certified_by_library` | false | The sufficient library method did not certify eligibility; no physical impossibility is asserted |
| `unresolved_computation` or unsupported information | null | Qualification is unresolved and selection must be blocked |
| Worker timeout, crash or interrupted start | null | Attributed execution failure retained without retry or eligibility substitution |

The exact-information-set assumption is material. Covariance-only and outer-only inputs are unsupported by this qualifier; their corners cannot supply attainable witnesses. The negative search uses a bounded set of legitimate directional points and constant uncertainty realizations. Absence of a found witness is never an impossibility claim.

## Runtime and record handling

`jobs.py` provides a qualification-only development coordinator with one to four fresh spawned workers. It retains real clocks, the 15-second whole-case watchdog, explicit case IDs and the last recorded phase. No other user process is terminated. A source/input-bound header, exclusive batch lock, immutable result publication and start markers prevent silent replay or concurrent writers. A failed worker remains unknown; other queued work can finish without converting the failure to an excluded scientific case. The old `evaluation.execute` entrypoint and its frozen resumption prohibition remain unchanged.

## Validation

`protocol.json` specifies 142 development, calibration, already-retired diagnostic and analytical inputs before the main repair validation. They are run once serially and once with four workers. The 38 retired/analytical inputs receive three further four-worker repetitions for execution testing. These are not independent scientific replicates or a protected population. No fresh protected outcome is accessed. The original 48 pilot qualification records supply a separate non-reexecuted agreement check. Analytical tests cover closed union geometry, narrow excursions, tangencies, uncertainty, queue witnesses, invalid witnesses, state resets, time gaps, cache identity, arithmetic errors and failure/resume behavior.

Run from the study root in the existing isolated baseline environment, with `SAL_EVIDENCE_ROOT` set to the unchanged historical checkout and `OPENBLAS_NUM_THREADS=1`:

```sh
python -m pytest -c pyproject.toml --confcutdir=. qualification_repair_v1/tests
python -m qualification_repair_v1.validation --verify qualification_repair_v1/recorded
```

The verification command replays saved accepted fixed actions through the original full-schedule checker, rather than regenerating qualification searches or policies. Explicit developmental repetition uses `--output` with a new private directory and retains its own receipt. Timing measurements cover this declared local development set and are not a worst-case guarantee, processor reliability result, physical validation or controller-superiority evidence. All previously published evidence and the failed attempt remain unchanged.
