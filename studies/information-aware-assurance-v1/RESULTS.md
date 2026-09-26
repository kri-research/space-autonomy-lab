# SA01 engineering fixture results

Original source commit `146f89e02fccbfd4a4fb56871a96d03e611888bc`; current source
commit `a8871f1617b1ff2c439d3f36960956767b91450f`. These are nine named deterministic engineering
fixtures selected for wiring and failure semantics. They are not a comparative
scientific population, operational fault sample or demonstration of practical benefit.

| Fixture | Admitted decisions | Late / lost responses | Protection gap (s) | Continuous model containment proved | Mission dwell proved |
| --- | ---: | ---: | ---: | --- | --- |
| nominal | 60 | 0 / 0 | 0 | Yes | No |
| delayed_dropout_and_correlated_bias | 60 | 0 / 0 | 0 | Yes | No |
| bounded_actuator_degradation | 60 | 0 / 0 | 0 | Yes | No |
| late_and_missing_decisions | 47 | 2 / 11 | 2.5 | Yes | No |
| unsupported_checker | 0 | 0 / 0 | 5 | Yes | No |
| coast_entry_failure | 0 | 0 / 0 | 3 | No | No |
| outside_model_actuator | 60 | 0 / 0 | 24 | Yes | No |
| invalid_timestamp_and_range | 60 | 0 / 0 | 0 | Yes | No |
| work_budget_exhaustion | 7 | 0 / 0 | 3.3 | Yes | No |

## Interpretation

The nominal 30 s approach retains continuous model containment and a valid conditional
prefix/coast lease throughout. Its final numerical state is approximately
`(0.0444, -40.3275, -0.00582, 0.04833)` in SI units. The prescribed two-second
terminal dwell is not proved. We retain that result rather than changing the
horizon, target tolerance or controller to manufacture mission completion.

The delayed/dropout fixture remains in finite coasting: the fixed acquisition
schedule and conservative age acceptance do not provide a timely matched pair.
This exposes an information/timing limitation, not evidence of successful active sensing.

The two deliberately late replies are rejected. Eleven lost replies produce a
2.5 s interval without a credited protection lease. Model containment on the
realised fixture does not erase that protection gap. The 40 mJ work-budget
fixture has a 3.3 s gap after the last valid coast expires.

With the checker disabled, all ten checking results are unsupported and no
command is admitted. The entry-failure fixture leaves the research box in the
numerical trace at 50 ms; the interval evaluator first loses containment resolution
on the 30-40 ms segment. Neither number is presented as an exact physical exit time.
Collision and keep-out avoidance still have finite-model evidence in this example.

Effectiveness 0.2 lies outside the credited [0.8,1] model after 6 s. The remaining
24 s receives no conditional assurance credit, even though the realised trajectory
has a continuous containment bound under its separate actual-input evaluation.
No fault-detection ability is inferred from the evaluator knowing the injected fault.

All nine fixtures retain a false mission-completion result. These engineering
checks establish working interfaces, physical distinctions and failure accounting;
they do not establish controller superiority, full recovery or mission utility.

## Reproduction and evidence limits

`recorded_sa01_final/` contains the current complete event records, summaries and
source-bound manifest; `recorded/` preserves the first execution unchanged. No fixture exception or omitted case occurred in the recorded execution.
The fixture source was committed before recording; all unit and development logs
remain separately retained in the private stage record. Earlier research was not rerun.

Run `python -m iaa.artifact verify recorded_sa01_final --replay` in the documented Python
environment to re-execute the reference loop and compare all summaries and traces.
The verifier also checks the actual source Git blobs and the published manifest
identity in the chosen checkout, not merely filenames or co-edited checksums.

Latencies and workload costs are modeled, not target-processor measurements.
Continuous inclusion concerns the specified mathematical HCW model. The evaluator
and guard share the rational inclusion algorithm; the independent closed-form
plant and matrix-series tests provide numerical corroboration, not physical validation.
External mission-engineer review, actual sensor bounds and hardware validation remain absent.

## Interface correction and complete repeated engineering execution

Before merging SA01, adversarial fixtures showed that the checking-result interface
accepted an unsupported scope and that the sink accepted an expiry later than the
proved three-second reserve. Both are rejected by the corrected implementation,
with regression tests covering the unknown scope and a one-millisecond overclaim.
The newly committed source was executed on all nine original engineering inputs.
Every JSONL event trace and the complete summary match the first execution exactly;
only the manifest and its source identity differ. The real interface defects did
not change the outcomes of the original well-formed fixtures. No controller, sensor,
geometry, horizon, terminal condition or budget was retuned. Both executions remain
available, and neither is an independent scientific population or hardware test.
