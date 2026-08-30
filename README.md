# KRI Space Autonomy Lab

**Executable research for trustworthy spacecraft autonomy.**

Space Autonomy Lab is KRI's open-source research testbed for studying how onboard autonomy behaves
under faults, uncertainty, and runtime safety constraints. It is designed as a technical companion
to **KRI-STD-001, Trustworthy Onboard AI Standard for Safety-Critical Space Systems**.

KRI-STD-001 defines a written assurance framework. This repository makes selected concepts
executable so they can be tested, measured, challenged, and improved.

> **Research software only.** This is not flight software, a spacecraft simulator of record, a
> regulatory tool, or evidence of KRI-STD-001 conformance.

## What v0.1 tests

The initial experiment models a simplified autonomous proximity operation. A learned policy attempts
to approach and hold near a target while KRI injects faults and compares three configurations:

1. deterministic baseline;
2. learned policy without runtime protection;
3. learned policy behind an independent runtime-assurance monitor and deterministic fallback.

Fault scenarios include range-sensor bias, sensor dropout, model corruption representing an SEU-like
event, and actuator degradation.

The benchmark records mission success, collisions, unsafe-state exposure, safety interventions,
recovery, final state, and propellant use.

## KRI-STD-001 connection

The testbed currently exercises selected ideas from:

- **§4.1** Simplex architecture, deterministic safety controller, decision gate and Safe Flight Envelope;
- **§4.2** bounded constraint checking, with an explicit limitation that this is not formal reachability proof;
- **§4.3** model identity/integrity evidence and unexpected-hash handover;
- **§4.4** fault injection and graceful-degradation experiments;
- **§5.1** independent runtime assurance and handover;
- **§5.2** reconstructable decision evidence with a hash-chained event log.

See [the detailed mapping](docs/kri-std-001-mapping.md).

KRI-STD-001 v1.3 is available at:
https://www.kri.org.uk/publications/trustworthy-onboard-ai-standard-for-space-systems

## Install

The research environment is locked to the Python patch and package versions in
`.python-version` and `uv.lock`.

```bash
uv sync --frozen --extra dev
```

## Public RPO demo — start here

Build the checked-in deterministic controller example, run the declared fault suite and assessment
policy through the existing product APIs, and open a standalone local page:

```bash
uv run python -m kri_space_autonomy.demo build --open
```

The shareable bundle is written to `demo/rpo-benchmark/` as stable JSON, concise Markdown, and
self-contained HTML. It has two deliberately separate layers:

1. **Try the harness:** an illustrative product run showing controller → deterministic faults →
   criteria report. It is not scientific evidence.
2. **Frozen architecture evidence:** a traceable summary of complete final aggregate results. The
   direct-measurement Experiment 002 campaign was favorable under its frozen gates. The
   estimator-in-loop Experiment 003 campaign was inconclusive: H1 was exactly zero with 95%
   interval `[0, 0]`, so H2 was not tested; descriptive mission-success degradation was concentrated
   in E5/E6.

See the [public demo guide](docs/public-rpo-demo.md). This remains a simplified one-dimensional RPO
controller test harness—not full GNC, formal verification, certification, or flight-safety evidence.

## Bring your own controller

External Python controllers can be loaded by import path without changing simulator or historical
experiment source. See the [controller adapter guide](docs/controller-adapter.md) for the small
observation/command contract and validation commands.

```bash
uv run python -m kri_space_autonomy.controller_adapter \
  validate kri_space_autonomy.examples.proportional_controller:controller
```

## Run a deterministic fault suite

The product-facing [fault-suite facade](docs/fault-suite.md) applies repeatable observation and
actuator faults to an external controller without editing simulator or historical experiment code.
The checked-in example covers nominal, observed-range bias, navigation dropout, actuator
effectiveness, and a composed case.

```bash
uv run python -m kri_space_autonomy.fault_suite \
  validate fault-suites/example-rpo.json

uv run python -m kri_space_autonomy.fault_suite \
  run-suite kri_space_autonomy.examples.proportional_controller:controller \
  fault-suites/example-rpo.json
```

This is a simplified RPO controller test harness, not a full GNC stack or flight-safety/
certification system.

## Produce an assurance evidence report

The product-facing [assessment report layer](docs/assurance-report.md) implements the workflow
**run controller → inject repeatable faults → produce assurance evidence report**. Acceptance
criteria are declared in a strict versioned policy; output is stable JSON plus concise Markdown.

```bash
uv run python -m kri_space_autonomy.assurance_report \
  assess kri_space_autonomy.examples.proportional_controller:controller \
  fault-suites/example-rpo.json assessment-policies/example-rpo.json \
  --json-output reports/example-rpo-assessment.json \
  --markdown-output reports/example-rpo-assessment.md \
  --stdout none
```

The report is evidence from this simplified test harness. It is not formal assurance,
certification, or a flight-safety claim.

## Run an experiment

```bash
kri-space-lab run scenarios/sensor-dropout.json \
  --controller protected \
  --evidence results/sensor-dropout.jsonl
```

Verify the evidence hash chain:

```bash
kri-space-lab verify-evidence results/sensor-dropout.jsonl
```

## Compare controllers

```bash
kri-space-lab benchmark scenarios/*.json --output results/baseline.json
```

## Check the bounded safety envelope

```bash
kri-space-lab verify-gate
```

This finite property check is useful for regression testing. It is deliberately **not** described as
formal verification or reachability analysis.

## Repository structure

```text
src/kri_space_autonomy/   core environment, policies, safety, faults and evidence
scenarios/                reproducible experiment definitions
tests/                    regression and safety-property tests
docs/                     KRI-STD-001 mapping, product guides and research roadmap
demo/rpo-benchmark/       deterministic public JSON/Markdown/HTML bundle
results/                  checked-in benchmark and frozen campaign results
```

## Research direction

The first programme studies autonomy, faults, runtime safety and recovery in space systems. Later
work will increase physical fidelity, move onto representative edge hardware, and investigate safe
online adaptation and continual learning under enforced operational constraints.

See [Experiment 001](docs/experiment-001.md), the
[Experiment 002 design-validation pilot](docs/experiment-002.md), the
[Experiment 002 final confirmatory campaign](docs/experiment-002-confirmatory.md), the
[Experiment 003 estimator-in-loop programme](docs/experiment-003.md), the
[Experiment 003 final confirmatory campaign](docs/experiment-003-confirmatory.md), and
[the research roadmap](docs/research-roadmap.md).

## Citation

If this software contributes to published work, cite the repository and KRI-STD-001 where relevant.
A `CITATION.cff` file is provided for citation tooling.

## Licence

Apache-2.0.
