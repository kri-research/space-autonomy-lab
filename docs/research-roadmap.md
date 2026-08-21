# Research roadmap

## v0.1 Executable assurance concepts

Research question: **What changes when a learned spacecraft-autonomy policy is placed behind an
independent runtime safety monitor and deterministic fallback controller?**

Deliverables:

- reproducible proximity-operation environment;
- deterministic and learned controller fixtures;
- Safe Flight Envelope decision gate;
- runtime-confidence handover;
- sensor, model and actuator fault injection;
- minimum evidence bundle with a tamper-evident hash chain;
- baseline benchmark across controllers and fault scenarios.

## v0.2 Robustness campaign

Add Monte Carlo sensor noise, combined faults, shared-cause failures, stronger metrics, confidence
calibration, and statistical reporting.

## v0.3 Higher-fidelity autonomy

Introduce replaceable policy adapters and higher-fidelity relative dynamics. Compare multiple
learning approaches under identical faults and safety boundaries.

## v0.4 Hardware evidence

Measure runtime-assurance overhead and recovery behaviour on representative edge hardware.

## v0.5 Safe adaptation

Study whether an onboard learner can update after deployment while remaining inside an enforced
safety envelope. This is the bridge from the current space-autonomy programme to KRI's future
continual-intelligence research.
