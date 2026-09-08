# Relationship to KRI-STD-001

Space Autonomy Lab is a complementary research implementation for **KRI-STD-001, Trustworthy
Onboard AI Standard for Safety-Critical Space Systems, version 1.3**.

It does not replace the standard and does not by itself establish conformance. KRI-STD-001 remains
the written assurance framework. This repository provides executable experiments, benchmark
interfaces, and evidence patterns that can test selected ideas and inform later normative revisions.

## Current mapping

| KRI-STD-001 area | Repository support | Current evidence status |
| --- | --- | --- |
| §4.1 Simplex architecture | Learned-policy fixtures, deterministic safety controller, independent-monitor configurations | Implemented in simulation and exercised across the programme |
| §4.1 Decision gate / Safe Flight Envelope | Runtime gate rejects out-of-envelope actions and records intervention evidence | Implemented in the public harness and experiments |
| §4.2 Constraint verification | Finite bounded state/action checks and independent physical endpoints in later experiments | Partial; **not** formal reachability proof |
| §4.3 Model integrity | Model/source identities and frozen configuration/evidence hashes are recorded; unexpected identities can trigger handover in protected fixtures | Partial; no complete signed-uplink or training-data provenance architecture |
| §4.4 Resource-constrained resilience | Sensor, estimator, model, packet-dropout and actuator faults; HCW and nonlinear-truth transfer studies | Simulation evidence only; no ECC, scrubbing, FPGA or radiation-hardware claim |
| §5.1 Runtime assurance | Independent monitor checks confidence/safety constraints and can hand over to deterministic control | Implemented and tested under multiple dynamics boundaries |
| §5.2 Forensic auditability | Hash-chained event evidence, frozen manifests, result hashes, replay identities, and explicit invalid-attempt records | Implemented for the research workflow |
| §6.2 HIL stress testing | Public controller/fault/report interfaces are designed to migrate to representative hardware | Not yet HIL |

## Experimental evidence relevant to the mapping

The completed programme deliberately increased the evidence boundary rather than treating one
simulation result as universal:

- **Experiment 002:** favorable direct-measurement 1-D confirmatory result under its frozen gates.
- **Experiment 003:** inconclusive estimator-in-loop 1-D confirmatory result.
- **Experiment 004:** valid, reproducible, inconclusive planar HCW confirmatory result. Both compared
  configurations had zero physical adverse events in the frozen primary population.
- **Experiment 005:** valid, reproducible, inconclusive nonlinear central-gravity confirmatory
  transfer result. Fixed-cell validity passed and the replay was byte-identical; both configurations
  again had zero physical adverse events in the frozen primary population.

The later saturated endpoints are useful assurance evidence because they show where the chosen
primary endpoint could no longer discriminate between the compared architectures. They do not prove
superiority or flight safety.

See the [benchmark guide](benchmark-guide.md), [Experiment 004 final result](experiment-004-results.md),
and [Experiment 005 final closeout](experiment-005-confirmatory-closeout.md).

## Why this repository exists

KRI-STD-001 calls for reviewable evidence around autonomy, runtime monitoring, resilience, and
incident reconstruction. A written standard alone cannot show the behavioural effect, limitations,
or overhead of those controls. Space Autonomy Lab makes selected requirements executable so that
assumptions can be challenged, metrics can be collected, null results can be retained, and future
versions of the standard can be informed by experimental evidence.

## Deliberate non-claims

- The repository includes simplified one-dimensional, planar HCW, and nonlinear central-gravity
  research models; none is a flight simulator of record.
- The learned policies and deterministic controllers are research fixtures, not flight models.
- The bounded checker is not formal verification or reachability analysis.
- The evidence mechanisms demonstrate reconstructability and integrity patterns, not a complete
  mission evidence architecture.
- Experiments 004 and 005 do not establish architecture superiority because their frozen primary
  physical endpoint saturated at zero events in both compared configurations.
- Passing the public harness or any experiment is not evidence of regulatory, insurer, customer, or
  KRI-STD-001 conformance.
- No 6-DoF or hardware-in-the-loop validity is claimed.

## Next standard-facing work

The completed Experiment 001-005 evidence is intended to support a separate KRI-STD-001 v2.0 effort:
formalising requirements, conformity levels, evidence expectations, verification procedures, and
links to reference tests. That standard revision remains separate from this repository's scientific
claims and from the stable release process.
