# Reproducing the completed property alignment studies

This additive index describes the completed scientific artifact at commit
`b2ff0cc3e0c5c0a524d248fa62d0f8ffc24d65b8`. Earlier scaffold READMEs and frozen
pre-execution statements retain their historical meanings. They are not current
claims that the subsequently recorded studies remain unexecuted.

## Isolated setup

Use a new full-history clone and CPython 3.13.5. The subproject is not installed
through the historical repository's Python 3.11 package configuration.

```sh
git clone https://github.com/kri-research/space-autonomy-lab.git sal-reproduction
cd sal-reproduction
git checkout --detach dc4c755d7d27c3a1eb4d10899b4ac55ee7deecac
git clone --no-hardlinks . ../sal-evidence
git -C ../sal-evidence checkout --detach 5539de5753092b09fd78351095292e7627047794
python3.13 -m venv ../sal-check-environment
. ../sal-check-environment/bin/activate
python -m pip install -r studies/property-alignment-v1/publication_v1/requirements.txt
export SAL_EVIDENCE_ROOT="$(cd ../sal-evidence && pwd)"
export OPENBLAS_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
cd studies/property-alignment-v1
python -m publication_v1.audit
python -m publication_v1.reproduce --output "$HOME/sal-check-output"
```

The final directory must not exist. The default reconstructs the frozen analysis
from retained records, verifies source/manifest bindings, tests explicit audit
fixtures, and regenerates spacecraft and cart result figures. It does not run a
protected policy, physical trial or host timing experiment. For an additionally
requested fixed-output numerical replay, add `--replay` with another new output
path. It checks the 73 stored developmental prefixes, ten individual recovery
traces, separate cart referee and the declared fixed-command event continuation.
Replay timings are new engineering observations, not replacements for recorded
budget outcomes. The original failed campaign must not be restarted.

The retained baseline diagnostics can be reproduced separately with `python
run.py audit`, `python run.py diagnostics` and `python run.py test`. They generate
new copies of the previously declared midpoint numerical diagnostic, not new
historical campaigns. Prior generated outputs are checkpointed automatically.
Original E004/E005 rows, stored replay subset and primary decisions are read only.

## Evidence and claim limits

The scientific input manifest names the earlier scientific commit and every
tracked source/data object there. It intentionally does not name the commit that
contains itself. The package's own source identities and fresh reproduction
results are recorded separately. Git identities provide reproducible content,
not independent custody or proof that the research is correct.

The studies distinguish historical paired outcomes, retrospective common-property
witnesses, controlled development, established protective baselines, a frozen
finite-prefix/obstruction diagnostic, prospective lagged-cart transfer and host
computer timing. They have different denominators and are never pooled.
The predictive comparator's better positive coverage, unresolved/late outcomes,
external continuation and actuator-model mismatch failures remain reported.
Finite prefixes are not full recovery. A verified shared-action obstruction is
not a successful protective intervention or individual-state impossibility.

No physical-system trial or independent human/laboratory review was obtained.
The numerical referee is separately implemented but comes from the same research
workflow. The host measurements are correlated observations on one computer, not
onboard hardware qualification or a worst-case execution-time bound.

## Historical profiles

The maintained Python 3.11.16 pipeline and dependency versions remain in the
original repository. Run `PYTHONPATH=src python tools/run_post_release_checks.py`
from the repository root with its locked environment. Its 208 tests and release
preservation checks are a distinct profile from the historical test collection.
The three known phase/source guard issues are explained in
`docs/post-release-maintenance.md`; neither guards nor old manifests are modified.
The E002d companion compressed planning file may be unpacked outside the checkout
for the documented isolated preparation. E005 CI/foundation/lineage differences
must be evaluated at their designated historical commits, not waived.

## Availability and rights

Existing raw records and numerical source are in this Git repository, with their
own source, protocol and data manifests. No new DOI, archive service or release
is asserted. Publication-quality long-term archival deposition still requires
an authorized repository deposit and its real returned identifier. The available
Git revision remains accessible independently of such a future deposit.
The repository's Apache-2.0 license applies to this added implementation, with
existing source notices retained. Cited papers remain under their own rights;
no publisher full text, private manuscript, grant proposal, workstation logs,
credentials or participant details are included here. Generative AI contributed
substantively to this code and internal audit; this is not independent peer review.

## Historical display regeneration

After the explicitly requested `run.py audit` and `run.py diagnostics` baseline
reproduction, use `python -m publication_v1.figures --data baseline/data --output
../baseline-display-check --local-pdf`. This displays the complete historical
paired tables, common-property ranges, retained midpoint paths and declared
geometry. It introduces no new statistical analysis. The manuscript's private
wrapper delegates to this same plotting implementation. Scientific plot input
and generator hashes are recorded in the final artifact manifest.

The public SVGs use a separate whitespace-only serialization step. Run `python -m publication_v1.prepare_figures raw.svg normalized.svg` on a new output path to obtain the deposited text representation. The figure manifest records raw and normalized hashes, the unchanged generator commit and the normalization-source hash. No geometric token or numerical value changes.
