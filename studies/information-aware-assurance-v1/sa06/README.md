# Finite spacecraft assurance assessment

`kri-assurance-eval` 0.1.0 packages KRI's supported observation reconstruction and
finite-command checker for **research design and evaluation**. It lets another
controller supply a proposed two-axis command and obtain a reproducible,
model-conditional assessment. It has no physical actuator backend.

This is not an improved mission controller. SA05 found no new goal acquisition
under any of the four schedules; the decision-aware candidate avoided requests
but had higher modeled cost. See [the complete results](https://github.com/kri-research/space-autonomy-lab/blob/16744cd7e14ae1a6c569231539635346a10b5e5b/studies/information-aware-assurance-v1/sa05/RESULTS.md).
The complete execution path did not establish reliable target deadlines.

## Install from public source

Use a new full clone, including the retained source branches, and CPython 3.13.5.
The component version is separate from the historical repository release/tag.
The component needs only the Python standard library at runtime. Installation
of the standalone wheel does not need Git, the large benchmark or private files.
Clone `https://github.com/kri-research/space-autonomy-lab.git` and enter
`space-autonomy-lab/studies/information-aware-assurance-v1`. For a fixed release,
check out the enclosing published commit before building. From that directory:

```sh
python3.13 -m venv /tmp/kri-sa06-build-env
. /tmp/kri-sa06-build-env/bin/activate
python -m pip install --require-hashes -r sa06/requirements-build.lock
python sa06/assemble.py --output /tmp/kri-sa06-source
export SOURCE_DATE_EPOCH=$(cat /tmp/kri-sa06-source/BUILD_EPOCH)
python -m build --no-isolation --outdir /tmp/kri-sa06-dist /tmp/kri-sa06-source
python3.13 -m venv /tmp/kri-sa06-use-env
/tmp/kri-sa06-use-env/bin/python -m pip install --no-deps /tmp/kri-sa06-dist/*.whl
cd /tmp
/tmp/kri-sa06-use-env/bin/python -I -m kri_assurance_eval.cli example
/tmp/kri-sa06-use-env/bin/python -I /tmp/kri-sa06-source/examples/controller_adapter.py
```

All output locations must be new. Use distinct suffixes on a second run; do not
replace prior evidence. The documented `release.json` source pin remains the
citable component identity after the normal merge. No new Git tag is required.
The build stage verifies original Git blobs, relocates imports into a private
namespace, and inventories every distributed source. Only the legacy protocol's
checkout-relative lookup becomes a package-relative import. The numerical
algorithms remain unchanged. See INTERFACE.md and source-map.json.

## Run and interpret

```sh
python -I -m kri_assurance_eval.cli contract
python -I -m kri_assurance_eval.cli assess --input request.json
python -I -m kri_assurance_eval.cli replay --input receipt.json
python -I -m kri_assurance_eval.cli benchmark --output /tmp/kri-sa06-host-new.json
```

The benchmark is a fixed internal host procedure with public engineering inputs,
retained warmups and failure statuses. It never restarts the protected SA05
campaign and never establishes physical energy, target latency or independent
replication. CLI assessment exit 0 means a finite conditional prefix, not mission
success; exit 2 is malformed/unsupported input, and exit 3 is another explicit
non-accepting result. Example exit 0 means expected statuses reproduced, including
negative examples. The snapshot and request schemas are documented in INTERFACE.md.

## Verification

```sh
python -m pytest -c pyproject.toml --confcutdir=. sa06_tests
python -m ruff check sa06 sa06_tests
python -m ruff format --check sa06 sa06_tests
python -m sa06.verify
```

The original full scientific evidence remains in the repository, not bundled into
this small wheel. Its frozen replay instructions remain in SA01-SA05. The local
benchmark, package build, internal integration and external evidence have separate
statuses. See RESULTS.md, EXTERNAL_VALIDATION.md and IMPLEMENTATION_NOTE.md.
The standard PDF, Excel checklist, website and existing manuscript are unchanged.
