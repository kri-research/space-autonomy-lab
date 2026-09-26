# Decision-aware sensing in KRI Space Autonomy

SA03 extends the existing research with one additional range/bearing request before
a fixed command application. It checks the complete possible reading range and a
missing-reading branch. The candidate prioritizes checked task-progress or goal-
eligibility changes rather than merely reducing a state-set width or fault count.

This is a simulation-only, finite-horizon development prototype. It does not establish
repeated control feasibility, real-time execution, hardware energy benefit, calibration,
full recovery or superiority to established active-sensing methods.

## Execute and reproduce

Use a complete Git clone with all retained source branches and CPython 3.13.5.
From `studies/information-aware-assurance-v1/`:

```sh
python3.13 -m venv /tmp/kri-sa03-env
. /tmp/kri-sa03-env/bin/activate
python -m pip install -r requirements-dev.txt
python -m pytest -c pyproject.toml --confcutdir=. sa03_tests
python -m ruff check .
python -m ruff format --check .
python -m sa03.artifact verify sa03/recorded_causal --replay
# New bounded development execution, never overwrite the published artifact.
python -m sa03.artifact run --output /tmp/kri-sa03-new-attempt
# Earlier source-bound evidence remains independently inspectable.
python -m iaa.artifact verify recorded_sa01_final --replay
python -m sa02.artifact verify sa02/recorded --replay
```

The runner performs thirteen named contexts with four schedules, fifty-two cells in
one new execution. It does not access final held-out outcomes or execute earlier
scientific campaigns. Unit/development exposure is explicit in protocol.json. All
failures and contrary cases are retained. Timing samples are genuine host observations,
recorded separately from deterministic results and never expected to repeat exactly.

## Component responsibilities

| File | Purpose |
| --- | --- |
| model.py | Typed information/clock/resource contract and single-request ledger. |
| forecast.py | Complete conservative future-reading partitions and continuous command checks. |
| policy.py | Fixed, uncertainty-triggered and decision-aware selection; complete tree verifier and simulated dispatch. |
| scalar.py | Exact small-system timing condition and contrary analytical examples. |
| development.py | Evaluation-only truth, declared cases, actual receipts, trajectories and comparison outputs. |
| artifact.py | Committed-source recording, complete membership/hash/Git-blob/mode verification and replay. |

The current record is recorded_causal/. REVALIDATION.md describes the causal receipt
correction and its separately measured timings. The first record and its RESULTS.md
remain intact and are interpreted as that original execution.

Read MATHEMATICS.md for the quantifiers, uncertainty bounds, application timing,
missing-observation handling and precise limited meaning of useful. RESULTS.md gives
the first execution; REVALIDATION.md gives the current execution. related-work.md distinguishes prior methods and access limits.

## Important operating boundaries

The supplied decision set is at 100 ms. A modeled 50 ms planning phase and 100 ms
request lead put acquisition at 250 ms. The first selected action applies at 700 ms,
lasts 500 ms and is followed by a three-second coast. Known queue and waiting commands
are checked. The entire selected tree is recomputed before simulated dispatch.
Actual host duration is separate from those illustrative latency assumptions.

A sensor option is useful for every admitted timely reading only if every retained
reading leaf has a checked useful common action. Missing, inconsistent or delayed
receipts use the already checked no-observation action, which need not be useful.
An unsupported leaf, invalid assumptions, exhausted search or late answer must not
be relabelled as a universal positive result. No SA02 outer corner is an impossibility
witness. Undetectable violation of a sensor bound can invalidate a nonempty result.

A decrease in squared target distance over 500 ms is a local task metric, not convergence
or full mission success. The same distinction applies to 500 ms goal eligibility versus
the existing two-second dwell. All simulated actions stop receiving a finite guarantee
at the declared endpoint. There is no physical actuator driver or infinite safe stop.

## Preservation and subsequent stage

SA01, SA02, prior property-alignment studies, E001-E005, recorded evidence and existing
releases remain unchanged. The retained feature branch keeps the source-freeze commit
reachable after normal squash merge. Only new code/evidence and research navigation
are added. Website, publication page, standard PDF, Excel checklist and the existing
manuscript are outside this execution.

SA04 may use a supported candidate or the documented simpler alternative; it must
address the actual execution costs rather than treating this modeled clock as a
measured deadline. No next stage is started by this module.

To reproduce the preserved first execution, use a separate clean full-history checkout
at eb5e899b42c270e4bf547f14903a2bd8de617a2a and its original command `python -m sa03.artifact verify sa03/recorded --replay`. Current verification deliberately rejects a first-run manifest paired with corrected source.
