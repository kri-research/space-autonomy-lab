# Research evidence mapped to KRI-STD-001

This is an implementation note for `kri-assurance-eval` 0.1.0 and the retained
SA01-SA05 research. It is not an amendment, checklist completion, safety case,
independent review or conformance statement. The first intended use is offline
design and evaluation. No assurance level for a real mission is assigned here.

## Authoritative edition

The current publication page was inspected on 27 September 2026:
https://kri.org.uk/publications/trustworthy-onboard-ai-standard-for-space-systems

The formal edition read in full was **KRI-STD-001-V2.0, 8 September 2026**, 16 pages:
https://kri.org.uk/publications/KRI-STD-001_Trustworthy-Onboard-AI-Standard_v2-0.pdf

PDF SHA-256: `4e9dbed7386de19069a56fa9a5f510ce94efc869afd4a2591eb083e3379c667b`.
Section numbers and printed page numbers below refer to that edition. The web
illustrations are informative; they are not the normative evidence standard.
The PDF and spreadsheet remain unchanged. This note maps relevant provisions,
not every applicable requirement of a future mission.

## Requirement-to-evidence mapping

| Formal provision | Evidence actually supplied | Gap or boundary |
| --- | --- | --- |
| Section 2.1, reviewed boundary (p.3); 2.4, terminology (p.4) | SA01 operating contract, SA04 timing model and SA06 INTERFACE.md identify state, input, observation and finite temporal scope. | Research geometry and declared sensor bounds are not a mission-approved ODD. Conventional control is not called AI solely because it is autonomous. |
| Section 4.1, Decision Gate and Protected Architecture (p.5) | SA04 actual-command checking and SA06 version/model/history validation separate a proposal from finite simulated admission. | No hardware-enforced bypass prevention, hostile-plugin isolation or physical authority boundary is established. |
| Section 4.1, Fallback and Recovery (pp.5-6) | Initial queue/coast is checked for its stated entry set and expiry; unsafe entry is uncredited. | Protection ends at 4200 ms. No sustainable recovery, indefinite stop or full mission continuation is supplied. |
| Section 4.1, Independence/Common Cause and Protection-Path Failure (p.6) | Separate SA04 processes, timeouts, fault fixtures, live-context regression tests and explicit trusted source closure. | Shared observation and rational flow code remain dependencies; process names do not prove mathematical or hardware independence. |
| Section 4.2, constraint arguments, reachability and implementation traceability (p.6) | SA01 rational inclusion, SA02 outer-state construction, SA03 outcome cover, SA04 initiation-window checks, SA05 nonlinear residual argument and separate numerical audit. | Conditional finite obligations only; no universal numerical roundoff proof, calibrated observation errors or continuing recoverability. The package preserves these limits. |
| Section 4.3, provenance and evaluation separation (pp.7-8) | Separate pilot, publicly deposited SA05 source/protocol before outcomes, complete paired records and source/data digests. | Hashes establish identity, not sensor truth, resistance to poisoning or external custody. |
| Section 4.3, model/software identity (p.8) | Pinned source closure, dependency lock, namespace transformation inventory, installed-byte checks and separate package version. | Tested host packaging does not establish deployed target identity. Authenticated uplink/rollback is not implemented. |
| Section 4.4, resource resilience (p.8) | Bounded messages/operations, explicit failure statuses, host timing and memory evidence, preserved overruns and no-energy-measurement flags. | Real power, thermal, radiation, target scheduling, physical communications and fault containment remain unmeasured. |
| Section 5.1, uncertainty and invalid inputs (pp.8-9) | Range/bearing timestamps, out-of-order processing, complete histories and explicit invalid/late/unresolved results. | Undetected bound violations can invalidate a nonempty set. No confidence score or covariance is treated as a deterministic bound. |
| Section 5.1, handover and recovery (p.9) | Simulated fixed application band, rejection after the deadline and finite-coast expiry. | Actual low-level handover, repeated switching, human/ground response and physical recovery remain unsupported. |
| Section 5.2, decision logging and incident reconstruction (p.9) | Source-identified request/result receipts, semantic recomputation, SA04 event-chain replay and tested normal/negative examples. | No physical acknowledgement, tamper-resistant storage, mission retention policy or uniquely proven incident cause. Self-hashed records do not authenticate themselves. |
| Section 6.2, review and evidence maturity (pp.10-11) | This mapping identifies controlled evidence paths and software/analytical/numerical/host boundaries. | Mission owner, acceptance criteria, competent independent reviewer and external review decision are not supplied. This is not a completed Level 3 review. |
| Section 6.3, prospective design, failure rules, preservation and reproducibility (pp.11-12) | SA05 prospective deposit, fixed 112 paired units/448 runs, missing rules, unchanged negative result, replay and independent numerical corroboration. SA06 has separate engineering inputs and its own source identity. | GitHub deposit is not externally administered preregistration. Local repetitions are not new independent spacecraft trials. |
| Section 6.3, result interpretation and evidence transfer (p.12) | Zero new acquisitions, no demonstrated candidate advantage, wide paired intervals and adverse sensor/timing findings remain visible. | No superiority, equivalence, flight reliability or transfer to a new mission/processor follows from these observations. |
| Section 6.4, reassessment and change history (pp.12-13) | New package/version and original source records are retained separately; incompatible requests are rejected. | Mission-specific reassessment and conformance suspension/reinstatement are outside this software release. |

## Controlled evidence locations

All SA01-SA05 locations below are fixed by commit
`16744cd7e14ae1a6c569231539635346a10b5e5b` in
https://github.com/kri-research/space-autonomy-lab . Their individual source/data
bindings remain in their manifests. The SA06 source identity is in `release.json`.

- `studies/information-aware-assurance-v1/CONTRACT.md` and `iaa/`.
- `studies/information-aware-assurance-v1/sa02/MATHEMATICS.md`, `RESULTS.md` and `recorded/`.
- `studies/information-aware-assurance-v1/sa03/MATHEMATICS.md`, `REVALIDATION.md` and `recorded_causal/`.
- `studies/information-aware-assurance-v1/sa04/MATHEMATICS.md`, `RESULTS.md` and `recorded/`.
- `studies/information-aware-assurance-v1/sa05/RESULTS.md`, `freeze.json`, `recorded/` and `sa05_validation/` alongside `sa05/`.
- `sa06/INTERFACE.md`, `RESULTS.md`, `release.json`, `recorded/` and `EXTERNAL_VALIDATION.md` in the same study.

## Requirement-level conclusion

No requirement-level contradiction in the edition was established by this package
integration. The pending items are evidence and implementation gaps against the
existing requirements. They do not justify weakening the standard or completing
its checklist. No normative revision is proposed here.

A future Space Autonomy page update could link the versioned software, reproduce
its limited purpose and retain the negative SA05 outcome. A publication-page link
would be informative only. Neither page is edited by this stage.
