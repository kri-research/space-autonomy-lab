# Post-release maintenance

The citable scientific snapshot is **v0.1.0**, commit
`f0e9e5d8c140ca3d5eea71cee97fd29f23bffe12`. The maintained branch can improve navigation,
metadata and checks without replacing that historical snapshot. Experiments 001 to 005 are
closed. Maintenance does not authorise a new experiment, campaign execution or release.

## Supported working environment

Use a full repository checkout, including history and tags, for the public demo and evidence
inspection. Run the following from the repository root:

```bash
uv sync --frozen --extra dev
uv run python tools/run_post_release_checks.py
uvx --python 3.11.16 --from cffconvert==2.0.0 cffconvert --validate
```

The first command uses the existing CPython 3.11.16 and dependency locks. The check runner uses
the same explicit test profile as CI, covering the direct and estimator-profile public interfaces,
fault suites, reports, demos, bounded gate checks, selected non-campaign scientific regression
tests, and release-preservation tests. It also runs the existing read-only E004 evidence verifier
and publication scan. It does not run a completed campaign or claim independent scientific replay.

The wheel and source distribution build successfully, but do not contain the repository-level
scenario, fault-suite, experiment or result data. The installed core gate checker works outside
a checkout; the default demo requires the checkout's data. Building a wheel is not a complete
portable scientific evidence distribution. Changes to that packaging contract need separate review.

## File roles

| Location | Retention and interpretation |
| --- | --- |
| `src/kri_space_autonomy/experiment_*` | Historical scientific implementations, including earlier amendments. Similar helpers can be part of distinct frozen designs. |
| Other `src/kri_space_autonomy/` modules | Public harness and adapters. These are also covered by historical source identities; changing behaviour requires an explicit compatibility and provenance review. |
| `experiments/` | Frozen designs, readiness records, seed contracts and published seeds. A pre-outcome statement remains a statement about that historical phase. |
| `results/` | Intentionally published outcomes, checksums, replay records, invalid attempts and closeouts. A result directory is not a scratch directory. |
| `artifacts/experiment-002/` | Published learned-policy fixture and its identity manifest. |
| `demo/rpo-benchmark/`, `demo/rpo-estimated/` | Intentionally published generated bundles for two different navigation profiles. Neither is a redundant copy of the other. |
| `scenarios/`, `fault-suites/`, `assessment-policies/`, `navigation-fault-plans/` | Public inputs and declared engineering acceptance criteria. Passing these criteria is not certification. |
| `docs/experiment-*` | Historical scientific narratives, including compressed design source and blocker/invalid-attempt records. |
| `tests/test_experiment_*`, `tests/conftest.py` | Historical regression and phase-selection logic. Retain rather than deleting guards merely because the phase changed. |
| `release/v0.1.0.json`, `docs/release-v0.1.0.md` | The original release manifest and release notes. Maintenance does not alter them or the tag. |
| `tools/`, this guide and maintained workflow files | Post-release inspection and maintenance tools, separate from scientific calculations. |

## Release preservation

```bash
uv run python tools/check_release_preservation.py
```

This read-only check compares **574 original paths** against the release's Git blob identities and
executable modes. It rejects missing or changed protected files and new files in scientific input,
source or evidence locations, including ignored new JSONL evidence. It checks the local release
tag's target and does not fetch, reset, regenerate or repair anything. Routine bytecode and the
known package installation metadata are excluded from new-scientific-file detection.

Six maintained paths have an explicit review exception: `README.md`, `CONTRIBUTING.md`,
`CITATION.cff`, the two workflow files, and `tests/test_release_metadata.py`. Those exceptions
permit maintenance; they do not make changes to these files automatically correct. New maintenance
tests and tools are reviewed in the PR. This guard reports **preservation**, not proof that every
historical manifest matches the current checkout or that the science has been independently verified.

The original publication workflow is retired. Its existing path now contains a manually dispatched,
read-only identity check. With authenticated read access, the same check can be run locally:

```bash
uv run python tools/verify_published_release.py
```

It checks the existing lightweight tag and published release against the fixed commit. Missing,
unavailable or mismatched metadata fails; there is no creation or repair fallback. The existing
release is not marked immutable in GitHub metadata. Administrative tag/release protection remains
a separate decision; the read-only workflow does not establish that protection by itself.

## Demonstration checks without overwriting published bundles

```bash
uv run python -m kri_space_autonomy.demo build --output ../sal-demo-direct-check
uv run python -m kri_space_autonomy.demo build \
  --navigation-profile estimated --output ../sal-demo-estimated-check
```

Use fresh output directories. Both profiles reproduced all four checked-in bundle files byte for
byte on the audit host with the locked runtime. These are small public engineering demonstrations,
not reruns of the completed scientific campaigns. Controller plugins execute trusted Python in the
current process; they are not sandboxed.

## Historical verification and known gaps

The initial full `uv run pytest` audit produced **284 passed, 3 failed and 32 deselected**.
The three failed assertions were:

- `tests/test_experiment_002d_workflow.py::test_historical_experiments_002_002b_002c_verify_unchanged`
- `tests/test_experiment_005_confirmatory_validation.py::test_complete_repaired_lineage_and_blocker_audit_are_preserved`
- `tests/test_experiment_005_transfer_pilot_workflow.py::test_foundation_source_hashes_and_readiness_identity_are_unchanged`

The first failure was the missing unpacked original design source. The following documented
preparation writes only a companion source file outside the checkout:

```bash
gzip -dc docs/experiment-002-research-plan.md.gz > ../experiment-002-research-plan.md
```

The affected E002d test then passed in isolation. The two E005 failures concern historical identities
that no longer match the released checkout, including the changed CI file. They are not repaired by
silently rewriting hashes, weakening assertions or deleting historical tests. `make test` still runs
the full historical suite; use the explicit maintained profile above for current public-interface CI.
The maintained profile must not be described as an all-tests or all-manifests pass.

A read-only inventory check found ten direct source-hash differences across frozen manifests and
two publication-manifest differences. Eleven of those expected historical versions were found in
fetched Git history. In particular:

- The E005 foundation and confirmatory CI hash is available at commit
  `46c6de41afa46e7e43b1c6074e59ba54dd3d99b8`; current operational CI is a different phase.
- The replacement-pilot publication manifest's versions of `docs/research-roadmap.md` and
  `tests/conftest.py` are available at `cf007e1cd7e44002069a8a5812867201d349f292`.
- The E002b freeze expects SHA-256
  `c45a7cb29489c94460f64560b6f85e578fbbd076b9f4d325116c463dcf75b1f1` for
  `experiments/002b/validation-evidence.json`. The released bytes have SHA-256
  `4168fa738e5023ef3d59b7b46f700e54ec4bf881e3144a63329be16b9a747a70`. The expected version was
  not located in fetched branch history. Its origin needs archival clarification, not a new freeze.

Across eleven checksum catalogues, 145 of 147 entries matched the release checkout. The two
mismatches are the replacement-pilot roadmap and `conftest.py` entries above. That catalogue uses
repository-root-relative paths; the other result catalogues use their documented directory-relative
paths. Both public demo manifests matched all listed file hashes and sizes.

The compressed E002 planning document also references an unavailable
`experiment-001-reproduction/REPORT.md`. The frozen source is retained unchanged; the reference is
an access gap, not permission to invent or regenerate its contents.

## E005 evidence availability

The released design and closeout agree on partition 53, 1,068 paired blocks and 2,136 episodes.
The closeout reports validity and byte-identical replay PASS, zero primary discordances, risk
difference 0.0, one-sided exact p = 1.0 and an INCONCLUSIVE decision. H1 failed; H2 was not formally
tested. The no-rerun decision and documented claim boundary remain unchanged.

The inspected release has no attached assets and contains no partition-53 campaign, materialised
seed or replay package. PR #31 introduced closeout documents, a closeout test and phase/CI updates,
not the underlying episode archive. Its `execution_summary_present` assertion is not an accessible
execution summary. Independent checking of execution and replay therefore remains unavailable from
these inspected surfaces. This does not establish that the records are absent from every other
location or invalidate the reported outcome. A separately approved archive of already-existing
records, with verified identities, is needed. Do not regenerate those records by rerunning E005.

E004 has 1,068 primary paired roots within a larger 1,452-block campaign. Its zero-event primary
result does not describe every episode: the separate actuator-degradation and disturbance-burst
strata recorded adverse events in both configurations. Those descriptive records and the E003
monitor/shared-fault descriptive mission degradation remain part of the published record. Keep
populations, endpoints and inferential versus descriptive conclusions separate.

## Public-interface and build issues awaiting approval

The legacy `verify-evidence` command prints `valid: false` for a tampered chain but returns exit
status 0. Its verifier also accepts an empty file or a schema-free self-hashed record; malformed
records can raise an unstructured exception. A valid prefix passes without an expected record count
or trusted terminal identity. The last limitation is inherent to an unanchored hash chain. The core
scenario loader accepts nonfinite JSON values. These behaviours were reproduced using temporary
fixtures only. Source and public API changes are intentionally deferred for explicit approval.

A dependency audit found one unique advisory affecting the pinned build backend, setuptools 80.9.0:
CVE-2026-59890 / GHSA-h35f-9h28-mq5c, concerning Unicode-normalisation bypass of source-distribution
exclusion patterns on relevant filesystems. The feed lists 83.0.0 as fixed. Duplicate feed entries
refer to the same advisory. No affected non-ASCII exclusion scenario or disclosed credential was
found here; the build archives inspected contained only ASCII member names. The dependency pin is
part of frozen provenance and has not been changed. Build-environment remediation needs a separate
review that retains the original scientific environment.

## Retention decisions

Retain invalid partition 44 records, invalid E005 pilot records, calibration-attempt files, historical
seed reservations, the compressed planning source, old phase helpers and both demo bundles. These
explain the experiment sequence and evidence identities. Their age or similarity is not a deletion
criterion. The `sal-v0.2.0-release` remote branch points to the already-reachable documentation commit
`6efaed4003970e56e2074385c3269bd03c32af49`; it is not a published v0.2.0 release. Branch deletion,
including squash-merged development heads that preserve distinct commit IDs, requires separate review.

No frozen file, completed result, statistical interpretation, public API, existing tag or release
was changed by this maintenance pass. No scientific evidence file is proposed for automatic deletion.
