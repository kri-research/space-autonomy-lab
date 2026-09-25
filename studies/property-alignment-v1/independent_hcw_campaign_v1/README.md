# Complete independent spacecraft certificate audit

This additive package reports a post hoc, read-only audit of the already frozen
768 selected spacecraft cases. The numerical implementation and protocol remain
unchanged in `independent_hcw_audit_v1/`, with audit identity
`bc472385b582d0f5d6ee9e7a3e4d5f250d316f2c6c9a4c8e31be21f838577f53`.
The original scientific source is `b2ff0cc3e0c5c0a524d248fa62d0f8ffc24d65b8`.

## What is checked

The reserve reader checks all 1152 original qualification records, the ordered
reserve, its two pre-execution retirements and the first 192 qualifying entries
per group. It does not rerun qualification or select a new population. Selected
singleton witness commands are independently checked numerically; the other
reserve proofs receive structural and content checks only.

Original delivered commands and dual weights are retained. Positive certificates
cover every complete initial box, the known queue and the held interval under
the original segment-wise uncertainty model. Negative certificates use actual
attainable origins and full-union necessary constraints. The original nine
unresolved and three late outputs cannot become retrospective online successes.

The frozen numerical receipts are retained losslessly. Original job files can be
reconstructed byte-for-byte from the pinned input and episode records; the
reconstruction is checked against the captured full attempt inventory. No
unavailable old experiment is generated to fill a missing record.

## Proof transcripts and units

R02 numerical receipts contain continuous-coverage counts rather than all leaf
boxes. A separately identified deterministic fixed-output replay observes the
unchanged core through a read-only Python profile callback and records every
accepted leaf enclosure. It must return exactly the first audit result; it cannot
replace that result or introduce a new command, dual weight or refinement rule.

Each transcript records exact time partitions, all four state enclosure endpoints
on the 2^-192 grid, and the sufficient corridor or ellipse inequality margin.
Corridor margins use the displayed scaled halfspaces in metres; ellipse margins
use the displayed quadratic in square metres. These are enclosure margins, not
Euclidean distances or independent tolerances for physical sensing/model error.
Every event interval must be fully covered for a verified prefix. Verification
reconstructs each leaf from original information and all admitted input intervals.
The 31 delivered obstruction records are also rebuilt using the original weights.

## Reproduce without running a policy

Use the existing Python 3.13.5 research environment and a full-history repository
clone, preserving the public branch containing the referenced reporter source.
From `studies/property-alignment-v1/`:

```sh
OPENBLAS_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python -m independent_hcw_campaign_v1.artifact verify
python -m pytest independent_hcw_campaign_v1/tests
```

The artifact verifier checks the fixed recorded audit and proof transcripts; it
never reruns the original controller, qualification library or one-second timing
experiment. Runtime of this offline check is only a verification cost. The
separate R02 auditor tests and the older publication tests are run in their own
documented test scopes to avoid duplicate test module names.

## Interpretation and provenance

Original descriptive diagnostic coverage remains 756/768. The independently
verified fraction is a separate post hoc summary and has no new confidence
interval. A nonverified certificate is not automatically a false physical claim;
numerical uncertainty, malformed evidence and an actual contrary witness remain
separate. Successful finite prefixes do not establish full recovery or mission
safety. Host/offline computation is not physical validation or independent human
peer review. Anonymous technical feedback informed this workflow. No government
or institutional endorsement is asserted.

The repository's existing Apache-2.0 license applies to the new implementation.
No manuscript, reviewer prose, personal information or private task logs are
published. Scientific inputs, original outcomes, R02 methods and all older
receipt versions remain unchanged.
