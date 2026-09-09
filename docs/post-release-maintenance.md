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
and a scoped publication check. The approved supplement adds real archive integrity, historical
catalogue and frozen pure-analysis recomputation checks. The publication wrapper retains the
original scanner and accepts only its exact new-opaque finding for the pinned supplemental archive,
after validating every member and scanning the expanded text. Any additional finding fails.
It does not run a completed campaign or claim independent simulation replay.

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
release is not marked immutable in GitHub metadata. A separate active tag ruleset,
`Preserve published v0.1.0 tag` (22598130), now restricts updates and deletions of the exact
`refs/tags/v0.1.0` ref with no bypass actors. It does not match main or make the release body
immutable. The read-only workflow verifies identity; it does not administer that ruleset.

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
  not located in fetched branch history. A subsequent authorised local archival search recovered
  the exact 1,372-byte expected payload from existing records. It is now separately provided in the
  [dated supplement](../supplements/2026-09-09-evidence-reconciliation/README.md), with sanitised
  provenance. Neither the frozen manifest nor the original published validation file was replaced.

Across eleven checksum catalogues, 145 of 147 entries matched the release checkout. The two
mismatches are the replacement-pilot roadmap and `conftest.py` entries above. That catalogue uses
repository-root-relative paths; the other result catalogues use their documented directory-relative
paths. Both public demo manifests matched all listed file hashes and sizes.

The compressed E002 planning document also references an unavailable
`experiment-001-reproduction/REPORT.md`. The frozen source is retained unchanged; the reference is
an access gap, not permission to invent or regenerate its contents.

## Explicit historical snapshot verification

Run these read-only checks from a full-history checkout:

```bash
uv run python -B tools/verify_historical_snapshots.py
uv run python -B tools/verify_evidence_supplement.py
uv run python -B tools/reconcile_e005_records.py
uv run python -B tools/check_reconciliation_publication.py
```

The historical tool reads authoritative manifests from fixed v0.1.0 and requires their working
copies to remain unchanged. It verifies eleven specifically designated historical Git identities
and one separately recovered E002b payload at its exact supplemental path. It retains the different
published E002b identity explicitly. The recovered payload is never attributed to an earlier Git
commit. Cite the enclosing merged commit for its public availability.

| Identity group | Historical source or separate binding |
| --- | --- |
| E002 package, dynamics and lock; E002b inherited dynamics | `15879624c68b8cf93709f4c108735495e368e649` |
| E002b Makefile and README | `2459cab197a1e759b50056bfee30416c4ced3013` |
| E004 confirmatory CI | `cfb56b2a5510916e5295ae9b654b3849f4a8d7e1` |
| E005 foundation and confirmatory CI | `46c6de41afa46e7e43b1c6074e59ba54dd3d99b8` |
| Replacement-pilot roadmap and phase controls | `cf007e1cd7e44002069a8a5812867201d349f292` |
| Recovered E002b expected validation | `supplements/2026-09-09-evidence-reconciliation/e002b-validation-recovered.json` |

Current bytes must match the designated historical identity, an exact reviewed release/PR #34
maintenance snapshot, or the one path-specific approved README correction digest:
`dafee53f8f0825c99011885ad69e92339ed5ab016525009373f96e1da530ac72`. This last binding permits precisely the reviewed correction; it does
not allow arbitrary future README or CI changes and does not require an unretained PR-head commit
after squash merge. Git replacement objects are disabled during identity reads.

The result distinguishes `MATCHED HISTORICAL SNAPSHOT`,
`CURRENT-CHECKOUT DIFFERENCE EXPLAINED BY PHASE HISTORY`, and `MATCHED RECOVERED SUPPLEMENT`.
A complete twelve-item content catalogue reports eleven historical matches, one recovered
supplement, no gaps/errors and exit 0. This does not assert complete custody or scientific validity.
Missing supplemental bytes produce an unresolved gap and exit 1; corrupt bytes, altered frozen
manifests, missing historical objects or unexplained current-file changes produce exit 2.
An optional `--e002b-record` checks an additional local payload but cannot waive a missing or
corrupt required public supplement. A remote URL never substitutes for the required local file.

The supplement verifier pins its manifest, archive and per-member inventory; it verifies actual
content and sizes in memory with no extraction. The recomputation loads only three unchanged
frozen analysis/configuration files under an isolated package name and checks the archived rows
against the newly dated output. It does not execute simulation or materialise seeds.

The maintained profile includes negative tests and real payload verification. The original
historical tests and phase-selection rules are unchanged. The previously reported full-suite
source-identity failures remain historical observations: their expected source phases are now
explicitly checked by this scoped catalogue. The full historical suite was not rerun for this
supplement, and its frozen pre-publication scanners can reject the newly authorised archive.
Neither those assertions nor the original scanners were weakened. The expanded publication
wrapper checks precisely the approved archive bytes; all other findings remain failures.

## E005 evidence reconciliation

The [9 September 2026 corrigendum](e005-corrigendum-2026-09-09.md) corrects the earlier
zero-absolute-adverse-event explanation. The additive supplement supplies the recovered 1,092-file
execution set and newly dated pure-analysis output. Both configurations record corridor departure
in all 1,068 episodes, with zero collision and keep-out flags. All 1,068 pairs are adverse in both
configurations: zero discordances, risk difference 0.0, one-sided p = 1.0, H1 failure and H2 untested.
The comparative decision remains INCONCLUSIVE. Hold acquisition occurs in all records; this is
compatible with an earlier departure because the two fields have different temporal definitions.

Strict type/membership checks and unchanged fixed-cell checks pass. The stored 32 replay rows
match the selected campaign rows byte for byte. No new simulation campaign or replay was executed.
The corridor interpretation was traced statically, with numerical-search and planar-scope limits
disclosed in the corrigendum. Complete physical trajectories were not recovered or revalidated.
Self-hashes, filesystem timestamps and hard-coded no-retry booleans do not independently
authenticate custody. The original execution summary still says analysis was pending; the new
output is expressly dated as a post-release recomputation, not a recovered original final analysis.

The original closeout and frozen release notes are preserved. The maintained README and additive
release-page warning direct readers to the corrigendum and supplement. The pre-warning release
body is retained verbatim with its SHA-256 in the supplement. No tag, release asset, software
version, original outcome file or frozen definition is changed.

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
criterion. After the owner-approved merge of PR #34, only `post-release-audit-hardening` and
`sal-v0.2.0-release` were deleted. The latter's commit
`6efaed4003970e56e2074385c3269bd03c32af49` remains reachable from main and v0.1.0, with no open PR,
release or deployment depending on that branch. Other historical development heads were retained.
Further branch deletion, including squash-merged heads, requires separate review.

All 574 protected baseline files, public scientific APIs and the original tag remain unchanged.
The E005 zero-absolute-event prose is corrected through the new notice, maintained README and
one additive release-description warning. The recovered supplement and recomputation are explicitly
separate from the original scientific snapshot. No scientific evidence file was deleted.
