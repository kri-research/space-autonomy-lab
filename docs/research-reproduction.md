# Research reproduction guide

Choose the research phase before installing dependencies or running checks.
The [research index](../studies/README.md) separates historical records, completed
property-alignment studies and later information-aware assurance work.

## Choose an environment

| Purpose | Environment | Instructions |
| --- | --- | --- |
| Original E001-E005 harness and maintained checks | CPython 3.11.16 with the root `uv.lock` | [Post-release maintenance](post-release-maintenance.md) |
| Completed property-alignment reproduction | CPython 3.13.5 with the reproduction package requirements | [Pinned reproduction instructions](../studies/property-alignment-v1/publication_v1/README.md) |
| Corrected finite-assurance component 0.1.1 | CPython 3.13.5 for the documented build and checks | [Component correction and installation](../studies/information-aware-assurance-v1/post_audit_v1/README.md) |
| External software integration exercise | CPython 3.13.5 and the full protocol commit supplied with the exercise | [EV01 protocol](../studies/information-aware-assurance-v1/ev01/README.md) |

Use separate environments. The historical root package and the later research
components are different installation targets; installing one does not install
the others. The original component 0.1.0 is retained for historical reproduction;
use the documented corrected 0.1.1 interface for the current integration exercise.

## Reproduce the property-alignment studies

Follow the [complete reproduction instructions](../studies/property-alignment-v1/publication_v1/README.md).
They specify a full-history clone, exact implementation and evidence commits,
Python version, dependencies, commands and new output directories.
Keep those instructions available when checking out the pinned implementation,
whose older README predates the separately recorded verification correction.

The verifier binds the historical scientific inventory, including its original
README bytes. Run the instructions in their specified pinned checkout, rather
than treating maintained `main` documentation as the historical snapshot.
The reproduction CI first rejects changes to existing property-alignment source
and evidence files from the scientific anchor. It then checks a separate scientific
checkout, with only the active reproduction package added outside that fixed inventory. It verifies
the original file contents and modes without relaxing the scientific manifest.

The default procedure audits stored evidence, reconstructs the frozen analysis
and regenerates result figures. Its optional fixed-output numerical replay is a
separate engineering check. Neither procedure starts a new scientific campaign,
replaces recorded host timings or establishes physical validation.

See the [Git content-binding correction](../studies/property-alignment-v1/publication_v1/corrections/git_binding_v2/README.md)
for the corrected verifier's exact source identity and limitations. Original
receipts remain historical records of the checks actually performed at that time.

## Inspect the original programme

Follow [post-release maintenance](post-release-maintenance.md) for the supported
root checks and [release notes](release-v0.1.0.md) for the original citable release.
The maintained test profile is separate from the full historical suite, whose
source-phase prerequisites and known failures remain documented. A passing
maintained profile does not mean every historical test or manifest passes on
current `main`.

Read the [E005 corrigendum](e005-corrigendum-2026-09-09.md) together with the
[recovered evidence supplement](../supplements/2026-09-09-evidence-reconciliation/README.md).
Invalid attempts, earlier protocols and superseded narratives are retained to
explain the sequence of evidence. They should not be deleted as duplicate files.
The maintenance guide also records legacy interface and build-dependency issues;
use isolated environments and only trusted local controller code.

## Preserve identities and outputs

Use full-history clones when a verifier requires Git objects. Downloaded source
archives and shallow clones do not provide all historical objects and source
branches required by the documented checks. Do not delete retained source refs
merely because a later change was squash-merged.

Write new diagnostic outputs outside the source and historical evidence checkouts.
Do not overwrite recorded results, change frozen manifests or restart completed
campaigns to obtain a different outcome. Failures, unresolved cases and correction
records remain part of the evidence.

For the original release, use [CITATION.cff](../CITATION.cff). For later studies,
cite their documented exact commit and component or protocol identity. The
`v0.1.0` citation does not identify all subsequent research. No new release or
archival identifier is introduced by this navigation guide.
