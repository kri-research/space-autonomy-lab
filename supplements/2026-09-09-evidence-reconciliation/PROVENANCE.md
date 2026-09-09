# Provenance and recovery notes

Prepared 9 September 2026. This supplement adds recovered records and new reconciliation metadata
to the preserved v0.1.0 scientific snapshot. It provides publicly inspectable content identities.
It does not retrospectively authenticate every historical event.

## E002b

`e002b-validation-recovered.json` contains the exact 1,372-byte UTF-8 payload recovered from
retained execution-output and file-read records. Extraction decoded the recorded text field and
copied its bytes without JSON reserialisation, whitespace normalisation or reconstruction.
Its SHA-256 matches the expectation already recorded in the unchanged
`experiments/002b/freeze-manifest.json`:

`c45a7cb29489c94460f64560b6f85e578fbbd076b9f4d325116c463dcf75b1f1`.

The original published `experiments/002b/validation-evidence.json` remains unchanged at SHA-256
`4168fa738e5023ef3d59b7b46f700e54ec4bf881e3144a63329be16b9a747a70`.
The recovered record does not replace it. The four differences are:

| Field | Recovered expected payload | Later published payload |
| --- | --- | --- |
| Validation timestamp | 2026-08-29T22:41:36.438038+00:00 | 2026-08-29T23:19:04.116127+00:00 |
| Dependency-lock duration summary | Checked 9 packages in 1ms | Checked 9 packages in 0.89ms |
| Test-duration summary | 36 passed in 2.24s | 36 passed in 5.73s |
| Publication scan file count | 96 | 112 |

Checks, pass/fail fields and the test count agree. The reason for the later replacement has not
been established and is not inferred here. Five matching text-field locations were found across
three retained archival files; some mirror the same output and are not independent witnesses.
The original private records, source-file identities and exact locators remain under owner control
outside this public repository. Their recorded times are evidence of what those records state,
not independently attested timestamps. Exact agreement with the pre-existing digest establishes
content identity, without proving complete historical custody.

## E005

The known execution checkout was at frozen design commit
`d841a016361974734bd28b27ff39e9df0e2cbaed`. The recovered set comprises three seed/index/selection
files and 1,089 campaign/replay/execution files, totalling 13,716,631 bytes. Every member was
copied byte for byte to separate owner-controlled staging. Donor files, branch and working tree
were not reset, cleaned, switched or regenerated. Source hashes, freeze/readiness bindings,
seed-index hashes, schedules, checkpoint hashes and assembled row bytes were checked.

The archive retains original repository-relative member paths and payload bytes. Tar ownership
is neutral, file modes are regular data-file modes, and member modification times use whole-second
filesystem values. The inventory preserves the observed nanosecond modification values separately.
These are recovery observations, not authenticated execution times. The inventory, archive,
checksums, index, provenance and reconciliation analysis are newly created supplemental metadata;
they are not presented as original historical publication manifests.

No original completed final analysis package was found. The unchanged execution summary says
`EXECUTION_COMPLETE_PENDING_FROZEN_CONFIRMATORY_ANALYSIS`. The supplied reconciliation is a new,
dated calculation of the unchanged frozen pure analysis on the recovered rows. It preserves all
recorded adverse flags and distinguishes absolute counts from paired discordances. Stored replay
records were compared, without running a new simulation replay.

## Public boundary

Only the identified scientific files, exact E002b payload and sanitised explanatory metadata are
published. Private session records, local machine paths and unrelated private context are excluded.
Every archive member was scanned as decoded text, after verifying the compressed archive and
individual payload identities. The read-only integrity checker rejects missing, additional,
corrupt, linked, traversal or oversized members. This is a bounded publication check, not a
universal guarantee that all historical evidence or every vulnerability has been independently verified.

`original-release-body.md` preserves the pre-correction release description verbatim.
`release-body-capture.json` records its observed release identity, capture time and SHA-256.
The only authorised release-page change is a dated warning prepended above those original notes,
linking to this supplement and the corrigendum at the final merged commit.
