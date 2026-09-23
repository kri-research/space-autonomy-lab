# Frozen evaluation attempt

The first attempt under evaluation identity `63eb088857849237bb9a4d42ac5ae38053c54335134a187c72d370f4a65d7ebd` stopped during qualification when a worker reached the frozen 15-second whole-case watchdog. The driver exited with code 1 after 244.2754 seconds. No candidate case, final selection, frozen analysis or confidence interval was produced. This is a protocol-invalid attempt.

Of 1,152 reserve inputs, 1,011 have completed eligible qualification receipts, four have start markers without completed receipts, and 137 were not started. The exception does not identify the triggering input. The four missing receipts are not all classified as timeouts; other active workers were stopped by the coordinator's cleanup. The underlying cause of the long computation remains unestablished.

`recorded_attempt/` preserves the complete available qualification receipts and start markers byte-for-byte. The empty advisory lock is omitted and identified in the execution receipt. Only the workstation path in the published failure trace is redacted; the original trace hash is retained. `recorded_summary/` contains accounting tables and a ledger of every planned reserve input. Passing the artifact audit does not make the campaign valid.

## Reproduce the accounting

Use the unchanged `protective/requirements.txt` and the pinned historical checkout specified by `SAL_EVIDENCE_ROOT`. From the study directory run `python -m campaign_v1.attempt campaign_v1/recorded_attempt` and `python -m pytest campaign_v1/tests`. These commands do not evaluate or retry protected cases. A new output directory may be supplied with `--output` to regenerate the accounting tables. `plot_attempt.py` reads the counts CSV using the local manuscript plotting environment; the figure describes execution accounting only.

## Scientific status

All source, method, population, endpoint, analysis and resource choices remain at the original freeze. The original runner blocks a started interrupted qualification. No failure was converted into ineligibility and no candidate denominator was formed. This attempt supplies no diagnostic coverage, controller comparison, collision rate, hold performance, operational safety or hardware-validation result.

The original identity and exposed qualification data must be retained. Further work requires a separately identified development and prospective freeze addressing qualification execution, with fresh protected inputs and explicit exposure accounting. The original watchdog must not be silently enlarged or its missing cases skipped. Task 09 is blocked for claims depending on a completed evaluation.
