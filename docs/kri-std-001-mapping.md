# Relationship to KRI-STD-001

Space Autonomy Lab is a complementary research implementation for **KRI-STD-001, Trustworthy
Onboard AI Standard for Safety-Critical Space Systems, version 1.3**.

It does not replace the standard and does not by itself establish conformance. KRI-STD-001 remains
the normative written framework. This repository provides executable experiments and evidence
patterns that can test selected ideas from the Green Paper.

## Current mapping

| KRI-STD-001 area | Repository support in v0.1 | Status |
| --- | --- | --- |
| §4.1 Simplex architecture | Learned policy paired with deterministic safety controller | Implemented in simulation |
| §4.1 Decision gate / Safe Flight Envelope | Runtime decision gate predicts next state and rejects out-of-envelope actions | Implemented in simulation |
| §4.2 Constraint verification | Finite bounded state/action checker | Partial; **not** formal reachability proof |
| §4.3 Model integrity | SHA-256 model identity is recorded; the protected configuration detects unexpected model-hash changes and hands over to deterministic control | Partial; no signed uplink or training-data provenance |
| §4.4 Resource-constrained resilience | Model-corruption and actuator-degradation fault campaigns | Partial; no ECC, scrubbing, FPGA or radiation hardware |
| §5.1 Runtime assurance | Independent monitor checks confidence and safety envelope, then hands over to deterministic control | Implemented in simulation |
| §5.2 Forensic auditability | Hash-chained evidence records include telemetry, commands, model hash, output, confidence, constraints and override reason | Implemented in simulation |
| §6.2 HIL stress testing | Fault campaign structure is designed to migrate to representative hardware | Not yet HIL |

## Why this repository exists

KRI-STD-001 calls for reviewable evidence around autonomy, runtime monitoring, resilience, and
incident reconstruction. A written standard alone cannot show the behavioural effect or overhead of
those controls. This project makes selected requirements executable so that assumptions can be
challenged, metrics can be collected, and future versions of the standard can be informed by
experimental results.

## Deliberate non-claims

- The environment is simplified and does not model orbital dynamics at flight fidelity.
- The learned policy is a lightweight research fixture, not a flight model.
- The bounded checker is not formal verification or reachability analysis.
- The evidence log is tamper-evident in the narrow hash-chain sense; it is not a complete mission
  evidence architecture.
- Passing the experiments is not evidence of regulatory, insurer, customer, or KRI-STD-001
  conformance.

## Planned research progression

1. Broader fault campaigns and statistical evaluation.
2. Replaceable policy adapters for external ML/autonomy systems.
3. Higher-fidelity RPO dynamics and explicit reachability analysis.
4. Representative edge-hardware measurements for latency and compute overhead.
5. Integration with established flight-software/simulation environments.
6. Safe online adaptation and continual-learning experiments under the same runtime constraints.
