# Contributing

Contributions should strengthen reproducibility, fault coverage, runtime-assurance experiments,
or spacecraft-autonomy research.

Before opening a pull request:

1. Keep experiments deterministic unless randomness is part of the stated research question.
2. Add or update tests.
3. Run `uv sync --frozen --extra dev` and `uv run python tools/run_post_release_checks.py`.
4. State which experiment, metric, or KRI-STD-001 requirement the change supports.
5. Do not describe simulation evidence as flight qualification or regulatory conformance.

## Post-release changes

Read [post-release maintenance](docs/post-release-maintenance.md) before changing historical files.
The maintained check profile is shared with CI. The full historical `pytest` suite has documented
phase/source prerequisites and unresolved lineage assertions; do not hide those failures or rewrite
frozen manifests to match a maintained checkout. Keep scientific changes, public API changes and
uncertain deletions approval-only. Preserve the existing release and tag, and do not run a completed
campaign or publish a replacement release as part of maintenance.
