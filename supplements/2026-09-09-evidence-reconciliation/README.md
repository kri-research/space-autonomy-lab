# Evidence reconciliation supplement

Prepared 9 September 2026 for Space Autonomy Lab v0.1.0, commit
`f0e9e5d8c140ca3d5eea71cee97fd29f23bffe12`. This additive supplement preserves the original
software, frozen designs, published records and tag. Read the
[E005 corrigendum](../../docs/e005-corrigendum-2026-09-09.md) before using the original E005 narrative.

## Contents

| File | Purpose |
| --- | --- |
| [e002b-validation-recovered.json](e002b-validation-recovered.json) | Exact recovered 1,372-byte validation payload matching the pre-existing frozen digest. |
| [e005-original-records.tar.gz](e005-original-records.tar.gz) | Lossless archive of 1,092 original E005 files, 13,716,631 member bytes, with original repository-relative paths. |
| [e005-inventory.json](e005-inventory.json) | Newly created complete per-member byte sizes, SHA-256 identities and observed source modification times. |
| [e005-reconciliation.json](e005-reconciliation.json) | Newly dated frozen-analysis recomputation, strict checks, independent absolute and paired counts, and recorded diagnostic ranges. |
| [PROVENANCE.md](PROVENANCE.md) | Sanitised recovery method, four E002b differences, custody and physical-interpretation limits. |
| [original-release-body.md](original-release-body.md) | Verbatim historical release description captured before the additive correction warning. |
| [release-body-capture.json](release-body-capture.json) | Newly recorded capture identity and hash for the original release description. |
| [manifest.json](manifest.json) | Hash and byte-size inventory of supplemental files, including the compressed archive. |

The E005 archive SHA-256 is
`3f0f71990c65159bfda70b79f24ca364bfaf12a736f2d1721844e032e9697b03`.
Its member inventory SHA-256 is
`0d33564bb1b979590adf9efc94f1046c158c5b4b2ddf8128bd912090fd48248e`.

The recovered E002b payload SHA-256 is
`c45a7cb29489c94460f64560b6f85e578fbbd076b9f4d325116c463dcf75b1f1`.
The original, different published E002b validation file and its frozen manifest are both retained.

## Verification

Use a normal full-history clone from the repository root. No private files are needed:

```bash
uv sync --frozen --extra dev
uv run python -B tools/verify_evidence_supplement.py
uv run python -B tools/verify_historical_snapshots.py
uv run python -B tools/reconcile_e005_records.py
```

The first verifier checks the pinned supplement manifest, actual file hashes and every archive
member in memory, including sizes, paths, duplicate names, links and expansion limits. It does not
extract files. The historical verifier distinguishes eleven historical Git matches from the separate
recovered E002b supplement. Its twelve-item identity catalogue is narrower than full provenance.

The final command compares a fresh calculation from the archived rows with the newly dated
reconciliation output. It uses only the unchanged frozen pure analysis and fixed configuration,
loaded under an isolated module name without importing the package root, campaign, simulation,
workflow or seed-generator modules. CPython 3.11.16, NumPy 2.4.6 and SciPy 1.17.0 are required.
The original numerical environment is retained for this bounded calculation; known build-backend
limitations remain disclosed in the maintenance guide.

The archived records contain 1,068 corridor-departure/composite-adverse episodes per configuration,
zero collisions and keep-out entries, and 1,068 pairs adverse in both configurations. The comparative
result remains INCONCLUSIVE. Fixed-cell PASS and matching stored replay records are scoped evidence;
neither authenticates all historical custody or independently revalidates physical trajectories.
No simulation campaign or simulation replay is performed by the commands above.

For citation, use this directory at the merged commit permalink supplied with the task completion,
plus v0.1.0 and the dated corrigendum. The enclosing Git commit binds these new supplemental bytes;
it does not make them part of the original release or create a new software release.
