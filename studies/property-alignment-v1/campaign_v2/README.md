# Frozen replacement diagnostic campaign

This is the completed replacement for the protocol-invalid first attempt. The
original attempt, historical campaigns and all frozen method code remain unchanged.
The invocation finished once on the bound Mac with four workers and one BLAS
thread each. The result concerns a finite common-command diagnostic, not a
complete mission controller or physical flight experiment.

## Results

All 1,152 reserve inputs were evaluated before selection. Of these, 1,151 qualified
and one had a checked precommand violation. The first 192 eligible inputs in each
of four synthetic strata yielded the fixed denominator of 768.

There were 725 common-prefix certificates and 31 checked HCW first-command
obstructions, giving 756 on-time verified diagnostic decisions (98.4375%). Nine
unresolved results and three decision-budget misses remain unsuccessful outcomes.
No selected outcome was missing and no whole-case watchdog or worker failure
occurred. The prespecified 95% conditional-mean interval is [93.5369%, 100%]. It
does not estimate flight safety or independent hardware reliability.

The fictional-mean shortcut had 93 confirmed false-safe admissions and three
unresolved rechecks. Pairwise compatibility admitted 181 of 192 applicable sets;
22 admissions coexisted with a checked full-set obstruction. These are descriptive
secondary counts. Native predictive and barrier methods each abstained on every
ambiguous set under their different information/continuation obligations, which
cannot establish candidate controller superiority.

## Data and verification

`recorded/raw_records.jsonl` preserves all 5,768 raw files byte-for-byte without
rewriting their timing or outcome fields. `manifest.json` binds every member. The line-delimited JSON contains each original filename and verbatim UTF-8 text, avoiding new opaque binary artifacts.
Explicit inputs, original analysis, complete qualification/selected-case ledgers,
matched categorical tables and timing summaries accompany the text bundle. The
qualification and candidate stages already performed all predeclared proof
rechecks. The reporting audit performs no new policy evaluation or trajectory
replay; it checks recorded identity, structure, algebra and unchanged analysis.

From `studies/property-alignment-v1/`, use the existing isolated environment with
`SAL_EVIDENCE_ROOT` pointing to the unchanged corrected historical checkout:

```sh
python -m campaign_v2.artifact --verify --output campaign_v2/recorded
python -m pytest campaign_v2/tests
```

To reproduce only the figures in an environment with Matplotlib:

```sh
python campaign_v2/plot.py --data campaign_v2/recorded --output /path/to/new-figures
```

Do not rerun the protected command to regenerate reports. A scientifically changed
method or new experimental run needs a separately identified prospective design.
The incomplete original campaign stays in `campaign_v1/`; it is not pooled into
this result. No independent human, laboratory or physical validation is claimed.
