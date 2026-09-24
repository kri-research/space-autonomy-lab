# Independent HCW certificate auditor

This is a separately implemented, post hoc checker for the frozen spacecraft
certificates. R02 builds and tests it. R03 must be invoked separately to audit the
full 768-case set. No primary campaign policy is executed here, and none of its
original outcomes or timing records is rewritten.

The numerical core uses 192-bit integer dyadic intervals and cancellation-safe
closed-form HCW maps for all four state components. Full initial boxes, known
queues, independent quarter-second uncertainty and continuous nonconvex-region
membership are supported. DERIVATION.md and contract.json state the exact model,
proof bounds, enumeration, assumptions and limitations. Source inspection and
reuse of the supplied analytical fixtures are disclosed; this is not clean-room
or independent human replication.

## Verification

From the parent study directory, run the new tests separately:

```sh
python -m unittest discover -s independent_hcw_audit_v1/tests -t .
python -I -S -B independent_hcw_audit_v1/worker.py --calibrate
```

The calibration file contains 24 named original development cases, three extra
explicit pairwise witnesses and eight previously exposed calibration receipts.
It does not contain any primary protected evaluation. All statuses, including
original abstentions, are retained. A source-only export and standard-library
interpreter are additionally used for dependency-isolation verification.
The online Taylor, candidate, protective and original geometry modules are never
imported by the numerical core, reader, tests or worker.

## Frozen audit

The frozen protocol binds the tested implementation revision, every input file,
all768original case/receipt identities, numerical settings, classification rules,
qualification checks and resource limits. All saved singleton qualification
witnesses for selected cases are checked. Their checks do not establish full
recovery or reselect the benchmark population. No new weights or actions are
searched for when validating the delivered primary certificates.

The runner requires --authorize-R03 and the exact frozen audit identity. Results
are written only to a new non-repository directory. Serial execution is deliberate:
no untested parallel scheduling is used. Only unstarted jobs may resume; a start
without a completed receipt remains interrupted and is not automatically retried.
A changed engine, proof budget or retry requires a new audit version, retaining
all earlier attempts. Offline timing is never substituted for the one-second
online decision budget. Numeric uncertainty and execution failure stay separate.

## Rights and provenance

The author authorized the supplied checker as project code. Its existing comments
and exact supplied JSON are preserved in reference_inputs. Anonymous feedback,
code provenance, computational separation and author approval are separate facts.
No government affiliation, institutional endorsement or formal peer review is
attributed. The existing repository license applies to this new implementation;
no reviewer prose or private manuscript is published by this package.

## Calibration and bounded resources

The final source-isolated test suite includes 95 unit/adversarial checks. Thirty-five
identified exposed development jobs are measured in three fresh warm calibration
processes and once with a fresh process per job. This is an engineering repeat,
not 140 independent scientific samples. Each run retains two original no-on-time
outcomes. The eight exposed original calibration inputs also exercise all eighteen
saved singleton qualification witnesses. No primary protected case has been
numerically evaluated by this engine during construction.

The offline audit permits at most 16,384 time-range cells per prefix with minimum
time width 1/65,536 s, using fixed 192-bit fractional arithmetic and ten series
terms. Each cold worker has a 30 s watchdog. One serial invocation stops launching
new jobs after 1,800 s; its last worker remains bounded by 30 s. These are resource
limits, not physical timing guarantees. Unknown or timed-out checks remain explicit.
Observed calibration timings and import traces are in validation/. New cases may
cost more; no worst-case execution time or full-campaign elapsed-time promise follows.

Resumption preserves the exact freeze and only executes unstarted jobs. A saved
receipt must still match the bound job, start marker and preserved worker bytes.
A started job without a completed receipt is labeled interrupted and is not retried.
The source requires CPython 3.13.5. Actual process timeout, crash, malformed-response,
checkpoint and corrupted-receipt fixtures complement mocked failure-path tests.
Source and receipt hashes support repeatability, not authenticated external custody.

The supplied checker is stored as `reference_inputs/independent_hcw_check.py.txt`
with its original exact byte hash. This is an immutable source-data snapshot,
not a runtime module. To repeat the original standalone reference calculation,
copy it as `independent_hcw_check.py` into a new private directory; it writes its
own output there. Dependency tests still parse this source snapshot. The added
numerical implementation is checked by the unchanged repository lint pipeline;
no historical code, test or lint rule is modified to accommodate this input.
