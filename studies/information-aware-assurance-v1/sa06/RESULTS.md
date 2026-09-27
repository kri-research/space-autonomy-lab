# SA06 software integration results

Component `kri-assurance-eval` 0.1.0 uses source commit `50003cb0511265afbe7c2f368d9fb19100ee4d44`. Its predecessor is `16744cd7e14ae1a6c569231539635346a10b5e5b`. This release packages the supported finite assessment functionality, not a superior mission controller.

## Installed component

The standalone wheel contains 34 members, including the 27 inventoried runtime source/data files and their source provenance. The observed wheel is 55,588 bytes and source distribution is 56,133 bytes. The archive identities are retained in `recorded/integration.json`. No third-party runtime dependency, Git checkout, private path or Basilisk installation is needed by the installed interface. The original Apache-2.0 licence is included.

The source closure is copied from actual pinned Git blobs; only import namespaces and the legacy filesystem lookup are relocated. Original versus packaged checker outputs are compared in the tests. The previous implementations and evidence are unchanged. The versioned facade checks observation history, model/frame/units, queue, completion time, command authority and finite expiry, and refuses externally supplied authority certificates.

A fresh isolated local environment installed the wheel without dependencies and ran all ten public examples and a separately launched consumer controller through public APIs. The process ran outside the source checkout with isolated Python import behavior. This is internal installation/integration, not an independent external evaluation. Both actual observation-conditioned and contradictory-observation cases are included.

## Bounded host observations

The committed procedure used one retained warm-up and two measured repetitions for each of ten engineering inputs: 30 calls, including 20 measured calls and ten warm-ups. All expected statuses matched. No input belongs to or restarts the frozen SA05 campaign.

| Input | Returned status | Measured median ms | Measured maximum ms |
| --- | --- | ---: | ---: |
| bounded_proposal | supported_prefix | 30.701459 | 31.252667 |
| zero_proposal | supported_prefix | 35.716916 | 40.495083 |
| late_check | late | 30.600729 | 31.310208 |
| missed_window | missed_application_window | 34.055937 | 37.220333 |
| unsupported_assumptions | assumptions_unavailable | 2.606292 | 3.086833 |
| excess_authority | unsupported_input | 16.861458 | 19.108958 |
| unsafe_entry | uncredited_entry | 8.107375 | 9.081792 |
| incompatible_model | unsupported_input | 2.466645 | 2.565666 |
| observation_conditioned | supported_prefix | 37.356167 | 40.210834 |
| inconsistent_observation | unresolved | 18.587812 | 18.987125 |

Measurements used CPython 3.13.5 on the originating Darwin arm64 host. The synchronous assessment includes installation-byte checks, encoding, observer reconstruction, initial-coast analysis, command checking and simulated admission. Startup, physical sensing/transport, clock alignment, physical actuation, durable logging and electrical energy are not measured by this procedure. Process CPU and memory high-water observations remain in the original records.

Negative and early-return inputs remain included; they must not be pooled into a successful-control throughput claim. These small assessment inputs, work scope and warm-up behavior differ from the earlier full planning path. The SA04 cold-path failures and SA05 planner overruns are not repaired or contradicted by these timings. A measured maximum is not a worst-case bound, and no real-time deployment readiness is asserted.

## Interpretation and remaining evidence

The package makes model-conditional diagnostics reproducible through an installable interface. A supported prefix is only a finite conditional result with command end at 1200 ms and protection expiry at 4200 ms. Zero proposals are explicitly not treated as effective changes from coast. Inconsistent input can leave the separately conditioned initial-coast argument available, but provides no new candidate authority; each assumption remains a separate condition.

The earlier prospective comparison found no new goal acquisition for any schedule. Request avoidance did not establish lower total modeled cost or superior mission behavior. That negative result remains unchanged and is not reinterpreted as a software-release success.

No actual target processor, calibrated rig/metrology, trial permissions or independently received integration report was verified in the scoped inspection. `EXTERNAL_VALIDATION.md` gives the minimal non-actuating boundary and conditions for future evidence. No physical motion, outreach, equipment purchase, package-index upload or new Git tag is performed.

Software release and internal installation are separately verifiable. Overall SA06 status remains **partially complete** because target measurements, physical trials and independent external integration/replication remain pending. This does not mark all six stages fully externally validated. The standard PDF, Excel checklist, KRI website/publication page and existing manuscript remain unchanged.

## Reproduce

Follow README.md to build/install from the exact source identity. `python -m sa06.verify` checks actual source Git blobs, complete original record membership and recomputed assessment semantics. Host time samples are identity/accounting checks, not targets for identical new measurements. File hashes do not establish sensor truth, physical action or external custody.
