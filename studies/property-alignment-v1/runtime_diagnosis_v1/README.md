# Qualification runtime diagnosis

This completes Task 08A only. The original failed campaign remains invalid and unchanged. No repair, new freeze, protected candidate run or manuscript revision is performed here.

## Finding

The isolated slow input is retired `timing_bounded_pair/137`. Its instrumented qualification completed in 95.488 s (94.679 s of process CPU), returning library-based ineligibility. The five preselected comparison inputs took 0.0346 to 0.0419 s for qualification; complete fresh-process calls took less than one second.

The trace records 26 trial actions, 194,468 time-range nodes and 96,973 ambiguous leaf intervals. Adjudication consumed 99.59% of qualification time; trajectory propagation consumed 0.303 s. All 26 sufficient full-box checks returned unresolved. This is repeated numerical work, rather than a missing terminal connection or a wait for an optimization service.

## Cause

`evaluation/qualification.py` tries all 13 actions for both hypothesis boxes. `candidate/certify.py` propagates and adjudicates the entire measurement-to-application queue again for each action. In `adjudication/engine.py`, unresolved interval membership recursively subdivides time to 1/4096 s. Subdivision of time does not remove uncertainty about the initial state: near a side wall the enclosures can continue to straddle the boundary even at a point in time. The expensive interval polynomial and exact-rational geometry calculations repeat without a dedicated early test of the immutable queue.

A separate, observation-informed diagnostic validates an attainable vertex and an allowed constant disturbance from each hypothesis. Both leave the corridor during the fixed zero-command queue, with first-exit brackets ending at 1.929199219 and 1.929565430 s. A new command cannot start until 2 s. At 2 s the checked outward side residual is approximately 0.000112 m in each witness. These are model-based existence witnesses, not physical measurements. An arbitrary corner of a propagated outer enclosure was not used as an attainable state.

Consequently, later trial commands cannot restore robust containment of this already-completed queue. This explains why a dedicated, sound queue-failure check is an appropriate repair target. Failed sufficient checks by themselves remain unresolved; the additional vertex witnesses supply the actual contrary evidence.

## Evidence and limits

The original protocol declared 13 diagnostic attempts over six retired inputs. Nine completed and four were censored, all retained. Two isolated plain executions and the four-process check of input 137 exceeded the separate 90-second diagnostic limit. The full cProfile attempt was censored at 240 s. A separately declared single-action profile then completed in 17.087 s and locates the work in interval range evaluation and rational geometry. Profiling timings include overhead and are not benchmarks. The [Python profiler documentation](https://docs.python.org/3.13/library/profile.html) defines self and cumulative time; cumulative rows must not be added together.

Original start markers place input 137 about 15.28 s before driver exit; the other three missing inputs started less than 1.15 s before exit. Together with `jobs.py` cleanup and the diagnostic results, this identifies input 137 as the timeout source under ordinary wall-clock continuity. The original exception omitted the case ID, so that attribution is an inference rather than a recovered per-worker failure record.

These repeated diagnostic inputs are now development evidence. Their original namespace is retained solely to reconstruct exact retired bytes. No old receipt is filled, no failed case is relabelled, and no protected coverage estimate is produced. Local timing does not establish worst-case execution time or a new runtime budget.

`recorded/manifest.json` binds the published JSON records. Binary profiles and personal execution logs remain local. `executed_source/` retains exact source for the two follow-up scripts before formatting; AST equivalence and both hashes are explicit. The original 13-attempt harness and all frozen scientific sources remain byte-identical.

## Reproduction

From the study root, using the existing isolated baseline environment:

```sh
python -m runtime_diagnosis_v1.summarize runtime_diagnosis_v1/recorded --verify
python -m pytest runtime_diagnosis_v1/tests
```

The first command only checks records. Tests additionally repeat the two small declared queue fixtures, not a campaign. An explicitly requested fresh diagnostic plan can use `python -m runtime_diagnosis_v1.run --output /new/private/diagnostic-directory`; its longer diagnostic watchdogs do not amend the original freeze.

## Next repair

Task 08B should introduce and validate an early immutable-queue check based on genuine attainable witnesses, avoid repeating unresolvable common-prefix work, and report the exact failing worker and phase. It must preserve conservative uncertainty labels and compare qualification semantics against the old implementation on development fixtures. Qualification resource limits must be calibrated separately from the unchanged one-second online decision budget. Re-freezing with fresh protected inputs and executing a replacement campaign remain Tasks 08C and 08D.
