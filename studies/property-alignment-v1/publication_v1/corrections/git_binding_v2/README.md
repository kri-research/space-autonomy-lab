# Git content binding correction

This is a post-publication verifier correction recorded on 2026-09-24.
It does not change the scientific snapshot, original results or frozen manifests.
The nonfrozen active `publication_v1.audit.verify_manifest` now invokes
`sal-git-content-binding/2`; `publication_v1.reproduce` uses the same repaired path.

## Defect and demonstrated correction

The previous implementation accepted a coordinated same-length substitution of
`README.md` and its in-memory manifest digest in an isolated full snapshot clone.
The actual Git blob did not change. The old function still reported the original
5,744-file scientific anchor. Version 2 rejects that exact preserved fixture.
Both the repaired check and the unmodified author-provided reference checker
verified all 5,744 real scientific files and 433,340,210 bytes with no mismatch.
Every entry in that snapshot has Git mode `100644`.

The trusted full commit is supplied by active verifier code, outside the input
manifest. The checker reads a NUL-delimited pinned tree, verifies available blob
objects in batches, computes Git object hashes over literal working bytes, and
checks the manifest size and SHA-256 against those Git-bound bytes. It also checks
Git file modes and symlink target bytes, and refuses unexpected parent symlinks.
It uses neither a moving branch nor the current index as its content authority.
Git replacement objects and inherited Git-routing environment variables cannot
substitute another source. Explicit empty input is rejected rather than replaced.

## Current source and commands

The implementation and mutation tests were committed before this receipt:
`793f4bd6c8139e88066f0cbf10e9c41a842ea875`. This separately named commit is retained on
`fix/publication-git-binding-v2`; its existence on a branch does not assert that
a later squash commit retains it as a main-branch ancestor. The older reproduction
source `dc4c755d7d27c3a1eb4d10899b4ac55ee7deecac` remains preserved on its original
research branch but contains the superseded verifier.

Use a full-history clone at the implementation revision with CPython 3.13.5 and
the existing `publication_v1/requirements.txt`, then from the study directory run:

```sh
python -m publication_v1.audit
python -m publication_v1.verify_recorded
python -m pytest publication_v1/tests
```

The first command checks the fixed scientific anchor. The second verifies the
unchanged original publication receipts and figure bindings. The third runs all
106 publication tests, including 76 new Git-binding regressions. Run the research
suite in its separate documented invocation because two historical test files
share the same Python module basename. No test is skipped or weakened.

## Verification scope

A supported POSIX host is required for descriptor-relative no-follow reads and
Git's owner-executable mode check. Other hosts fail rather than report a weaker
success. Expected symlinks are checked by literal target bytes, including broken
targets, without following the target; parent symlink traversal is rejected.
Submodules and unsupported object types fail explicitly. The trusted checkout
must remain stable during inspection. Git/Python integrity and cryptographic
collision resistance remain assumptions. Added paths outside the anchored tree
are not part of this historical content assertion.

The source and Git-mode checks, available-object checks, failed-before/passed-after
mutation, separate comparison and actual test counts are recorded in
`verification.json`. Its manifest refers to earlier source identities, not to a
self-referential current commit. The recorded comparison adds no physical trial,
new protected outcome, numerical certificate proof or independent human review.
The original `publication_v1/recorded/` and `evidence_manifest.json` are unchanged.

The Git tree fields and NUL output follow the official
[ls-tree documentation](https://git-scm.com/docs/git-ls-tree). Batched object
inspection follows [cat-file](https://git-scm.com/docs/git-cat-file). Literal object
hashes use the [Git object header](https://git-scm.com/book/en/v2/Git-Internals-Git-Objects).
