# Property alignment research workspace

This additive subproject preserves the original Space Autonomy Lab experiments and releases.
Its current executable content is the previously declared baseline diagnostic and read-only record audit.
No new causal experiment, revised controller, protected evaluation or physical trial is completed here.

## Baseline reproduction

Use Python 3.13.5 with the dependencies in this subproject's `pyproject.toml`, separately from the historical environment.
Provide a separate clean, full-history checkout at commit `5539de5753092b09fd78351095292e7627047794`.
From this directory:

```sh
export SAL_EVIDENCE_ROOT=/absolute/path/to/pinned-evidence
export OPENBLAS_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
python run.py audit
python run.py diagnostics
python run.py test
python -m pytest tests
python run.py verify --group audit
python run.py verify --group diagnostics
python run.py export --group audit --destination /absolute/path/to/local-paper/data
python run.py export --group diagnostics --destination /absolute/path/to/local-paper/data
```

Execution receipts bind the current baseline source and exact output bytes. Prior generated outputs are retained in local run snapshots before re-execution. Hash checks establish content identity, not independent custody or physical validation.

## Evidence boundaries

`claim_evidence.json` is the compact scientific index. `baseline_import.json` identifies the supplied source before path adaptation and formatting. Original modules in `baseline/source_evidence/` retain their exact Git blob identities and Apache license. The copied baseline protocol is historical local diagnostic provenance, not a new preregistration.

The baseline retains 84 existing validation cases. Separate integrity fixtures test the output exchange, not spacecraft protection. New research must use separate protocols and output namespaces rather than altering this baseline or any E001-E005 artifact. Matched statistics, read-only record analysis, numerical corroboration and physical measurement remain different evidence classes.

The unfiltered legacy suite's three source/lineage-guard failures remain documented in `docs/post-release-maintenance.md` at the repository root. The published maintained post-release checks are a separate profile. This subproject does not weaken either set of checks or claim a universal historical test pass.

Manuscript sources, prompts, workflow state, grant drafts, workstation paths and raw personal logs are intentionally excluded. No manuscript is published by this scaffold.
