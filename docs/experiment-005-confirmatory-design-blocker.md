# Experiment 005 confirmatory-design audit: NOT READY

## Decision

The partition-53 confirmatory design was **not frozen**. No partition-53 generator was added or
invoked, and no partition-53 seed, scenario, episode, checkpoint, or result file was created.

The audit stopped because the merged closeout commit does not satisfy the Experiment 005
foundation's exact frozen-source identity. This is a lineage/integrity blocker under the
programme's conjunctive fail-closed rules. It is not evidence for or against either configuration.

## Audited lineage

The checked-out branch starts at merged main commit `cf007e1cd7e44002069a8a5812867201d349f292`.
The reachable Experiment 005 chain is linear and contains:

1. `344dfe4` — nonlinear two-body truth foundation;
2. `27993dc` — partition-52 transfer-pilot design freeze;
3. `90de438` — preserved invalid partition-52 infrastructure attempt;
4. `a311c4f` — outcome-blind replacement-execution amendment reserving partition 54; and
5. `cf007e1` — valid partition-54 execution and closeout package.

The recorded immutable identities are:

| Object | Recorded identity |
|---|---|
| Foundation freeze | `921c481726d6f078621ff3a355a7803af803bdc61a8a2da07ffb974a433b3be8` |
| Foundation readiness | `9ec734543fd3580e9a2990a16dc56747a0f75334f76bd2c7ae1fdc3647732e67` |
| Transfer-pilot design freeze | `3fa9fd6e9e4d3146af6495c07599ed792cfb52ce16e90d0dca234ed64295be8b` |
| Transfer-pilot design readiness | `ebc98c9eb9b14d2dc85351d68ca3c5c84791e050f2be038c7fdd9067ef6ce2f3` |
| Replacement-amendment freeze | `01504ff16ccf8a79dad67f88c4d40920be39dfa929169ccb72fdfcede18b34c1` |
| Replacement-amendment readiness | `3181e1a9b40c3ab32b684934d8c975b3eeeee44c2b38cd9dc80e0f0c589328c0` |

The checked-in partition-54 package records 20 complete paired blocks, 40 episodes, zero retries,
zero replacement roots, zero infrastructure failures, and a byte-identical frozen 10-block replay.
The campaign and replay digests are respectively
`0a890fce567b0a6138c487b8ce34da5ed63ee8343a222e110434c832e05de338` and
`88435a577419c3e426ede0f1fd9191fcc40b30d041900fcabef117b54e4e21cb`.
Those records support a future design audit only if the complete frozen lineage still verifies.

## Blocking integrity finding

`experiments/005/freeze-manifest.json` freezes `.github/workflows/ci.yml` at SHA-256
`bc033a3ddc0114964059760a6372b8da233b8aac1026d24af2a795c5b607f420`.
The file retained that exact digest through parent commit `a311c4f`. Commit `cf007e1` changed it;
the current digest is
`780d88b9a36c5a7dd1190169e9971e220c4ed03da452c69b2ccd7951a770ac64`.

The live foundation verifier therefore reports:

```text
passed: false
errors_preview: ["frozen_foundation_source_hashes"]
source_mismatches: [".github/workflows/ci.yml"]
```

This propagates through the preserved invalid-attempt verifier, replacement-amendment verifier, and
partition-54 closeout verifier. The phase-aware full test run at `cf007e1` completed with 272 passed,
23 deselected, and 6 failed tests. All six failures trace to the same broken foundation prerequisite:

- `test_invalid_partition_52_attempt_is_preserved_and_verified`;
- `test_amendment_preserves_invalid_closeout_and_scientific_design`;
- `test_partition_54_execution_and_frozen_gates_validate`;
- `test_closeout_is_descriptive_and_leaves_partition_53_untouched`;
- `test_public_closeout_package_verifies_when_materialized`; and
- `test_foundation_source_hashes_and_readiness_identity_are_unchanged`.

The current test names may vary with collection order; the decisive evidence is the live
`foundation_identity` mismatch above. A fast closeout-package hash check cannot replace the failed
conjunctive lineage verifier.

## Partition-53 non-access evidence

The audit found:

- no current partition-53 seed or result path;
- no reachable Git history path under `experiments/005-confirmatory/seeds` or
  `results/experiment-005-confirmatory`; and
- no reachable materialized root matching `experiment005:53:<case>:<replicate>` in experiment or
  result artifacts.

Thus partition 53 remains unmaterialized and unexecuted, as required.

## Required next step

A separate integrity-repair review must resolve the protected CI-file mutation without rewriting or
weakening the historical freeze after the fact, and then rerun the complete phase-aware Experiment
005 lineage, replay/integrity, historical-result, privacy/provenance/secrets, Ruff, compilation, and
stable-product gates. Only a clean conjunctive result can make a new partition-53 confirmatory-design
freeze eligible for consideration.

No confirmatory question, endpoint family, threshold, case matrix, sample size, analysis rule, or
generator authorization was frozen in this blocked task.
## Resolution applied

The integrity repair restored `.github/workflows/ci.yml` byte-for-byte to the Experiment 005 foundation identity `bc033a3ddc0114964059760a6372b8da233b8aac1026d24af2a795c5b607f420`.
No Experiment 005 scientific source, frozen manifest, threshold, case, seed contract, or outcome artifact was changed. After restoration, the complete partition-54 closeout verifier passed with no missing evidence or integrity errors; Ruff, compilation, the stable gate, and diff hygiene also passed locally. Partition 53 remained unmaterialized and unexecuted throughout the repair.

To avoid spending GitHub Actions minutes on every research step without mutating the protected workflow again, non-milestone changes will use local validation and GitHub's `[skip ci]` convention; full hosted CI is reserved for major milestones and releases. This operational policy does not alter any historical Experiment 005 freeze or scientific decision.
