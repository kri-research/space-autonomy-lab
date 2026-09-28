# Post-audit input corrections

This is a correction to KRI's existing Space Autonomy research. It supplies
`kri-assurance-eval` **0.1.1** for offline design and evaluation. Version 0.1.0,
all earlier scientific sources and the frozen SA05 population/results remain
available unchanged. No package-index upload or new Git tag is implied.

## Changes and limits

A1 bounds observation scalars before rational construction in packet decoding,
assessment, estimation and the public observation helper. C1 ignores unavailable
packet content before it can change the reusable observer's present admissibility.
The public assessment and snapshot interfaces remain delivered-only. The corrected
observer is in the installed private runtime closure; historical `sa02/` and
`sa04/` code remains frozen and must not be mistaken for a patched implementation.

B1 adds a separately dated post-hoc SA05 goal-opportunity analysis. Eighty of the
81 initially ineligible in-model inputs cannot reach the goal in time under the
stated envelope; the remaining input is not proved feasible. The acquisition
comparison has almost no opportunity to discriminate sensing strategies. Original
counts, denominators, statistical calculations and adverse outcomes are retained.
See `sa05/posthoc_attainability_v1/README.md` in the research repository.

Read CORRECTIONS.md and INTERFACE.md in the assembled source package. This component
has no physical driver, continuing-recovery guarantee, calibrated-sensor claim,
measured energy benefit or real-time readiness. The SA04 deadline failures and
SA05 negative cost/acquisition findings remain valid within their stated scope.
Target, physical and external validation remain pending.

## Build from a full-history public clone

From `studies/information-aware-assurance-v1/`, with CPython 3.13.5:

```sh
python3.13 -m venv /tmp/kri-post-audit-build-env
. /tmp/kri-post-audit-build-env/bin/activate
python -m pip install --require-hashes --only-binary=:all: -r sa06/requirements-build.lock
python -m post_audit_v1.assemble --output /tmp/kri-assurance-0.1.1-source
SOURCE_DATE_EPOCH=$(cat /tmp/kri-assurance-0.1.1-source/BUILD_EPOCH)   python -m build --no-isolation /tmp/kri-assurance-0.1.1-source --outdir /tmp/kri-assurance-0.1.1-dist
python -m pytest -c pyproject.toml --confcutdir=. post_audit_v1/tests
python -m post_audit_v1.verify
```

Use new output directories; do not overwrite an existing assembly or record.
The normal clone retains source branches because squash merging alone does not
preserve every frozen source as an ancestor of main. The correction source and
source inventory are identified by `post_audit_v1/release.json`.

## Use without the checkout

```sh
python3.13 -m venv /tmp/kri-assurance-0.1.1-use
/tmp/kri-assurance-0.1.1-use/bin/python -m pip install --no-deps /tmp/kri-assurance-0.1.1-dist/*.whl
cd /tmp
/tmp/kri-assurance-0.1.1-use/bin/python -I -m kri_assurance_eval.cli example
/tmp/kri-assurance-0.1.1-use/bin/python -I /tmp/kri-assurance-0.1.1-source/examples/controller_adapter.py
```

The installed assessment has no third-party runtime dependency. Rebuilding the
source archive's contents requires the separately pinned build tools, but no Git
at that stage. Wheel equality and archive payload equality are checked separately;
source tar/gzip timestamps and ownership are not claimed byte-reproducible.
The source distribution is not the full scientific evidence repository.
