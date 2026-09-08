# KRI Space Autonomy Lab

**Executable research for trustworthy spacecraft autonomy.**

Space Autonomy Lab is KRI's open-source testbed for studying spacecraft autonomy under faults,
uncertainty, model mismatch, and runtime safety constraints. It is a technical companion to
**KRI-STD-001, Trustworthy Onboard AI Standard for Safety-Critical Space Systems**.

**Stable citable research release:** `v0.1.0`

> **Research software only.** This repository is not flight software, a simulator of record,
> certification evidence, or proof of KRI-STD-001 conformance.

## Current status

The first Space Autonomy Lab experimental programme is complete through **Experiment 005**. The
programme progressed from a compact one-dimensional proximity-operations harness to estimator-in-loop
experiments, planar HCW dynamics, and a nonlinear central-gravity truth model.

| Experiment | Evidence boundary | Final status |
| --- | --- | --- |
| 001 | Initial executable assurance concepts | Exploratory baseline |
| 002 | Direct-measurement 1-D confirmatory benchmark | **Favorable** under its frozen gates |
| 003 | Estimator-in-loop 1-D confirmatory benchmark | **Inconclusive** |
| 004 | Planar HCW confirmatory assurance study | **Valid, reproducible, inconclusive** |
| 005 | Nonlinear two-body-truth confirmatory transfer study | **Valid, reproducible, inconclusive** |

Experiments 004 and 005 both reached a saturated primary endpoint: neither compared configuration
produced a physical adverse event in the frozen primary population, so superiority could not be
established. Those results are retained as valid inconclusive evidence and are not rerun or tuned.

See the [benchmark guide](docs/benchmark-guide.md) for the evidence layers and the
[research roadmap](docs/research-roadmap.md) for what comes next.

## Benchmark layers

Space Autonomy Lab deliberately separates three things that are easy to confuse:

1. **Public deterministic harness**: bring a controller, inject declared faults, and produce a stable
   assessment report. This is an engineering example, not a scientific result.
2. **Frozen confirmatory evidence**: prospectively designed experiments with immutable analysis and
   replay evidence.
3. **Higher-fidelity research evidence**: planar HCW and nonlinear central-gravity studies used to
   test whether conclusions survive stronger dynamics and model mismatch.

The public demo embeds Experiments 002 and 003 because they share the one-dimensional product-harness
boundary. Experiments 004 and 005 are linked separately rather than collapsed into the same claim.

## Install

The environment is locked to the Python patch and package versions in `.python-version` and
`uv.lock`.

```bash
uv sync --frozen --extra dev
```

## Public RPO demo

Build the checked-in controller example, deterministic fault suite, assessment policy, and standalone
local report:

```bash
uv run python -m kri_space_autonomy.demo build --open

# Same controller through the frozen-estimator product profile.
uv run python -m kri_space_autonomy.demo build \
  --navigation-profile estimated --open
```

The direct bundle is written to `demo/rpo-benchmark/`; the estimated bundle is written to
`demo/rpo-estimated/`. Each contains stable JSON, concise Markdown, a self-contained HTML view, and a
bundle manifest with SHA-256 identities.

See the [public demo guide](docs/public-rpo-demo.md) and
[navigation profile guide](docs/navigation-profiles.md).

## Bring your own controller

External Python controllers can be loaded by import path without modifying simulator or frozen
experiment source.

```bash
uv run python -m kri_space_autonomy.controller_adapter \
  validate kri_space_autonomy.examples.proportional_controller:controller

uv run python -m kri_space_autonomy.controller_adapter \
  replay kri_space_autonomy.examples.proportional_controller:controller \
  scenarios/nominal.json --navigation-profile estimated
```

See the [controller adapter guide](docs/controller-adapter.md) for the observation/command contract.
Local plugins execute in process, so load only trusted controller code.

## Run a deterministic fault suite

```bash
uv run python -m kri_space_autonomy.fault_suite \
  validate fault-suites/example-rpo.json

uv run python -m kri_space_autonomy.fault_suite \
  run-suite kri_space_autonomy.examples.proportional_controller:controller \
  fault-suites/example-rpo.json
```

The checked-in example covers nominal behaviour, observed-range bias, navigation dropout, actuator
effectiveness, and a composed case. See the [fault-suite guide](docs/fault-suite.md).

## Produce an assurance evidence report

```bash
uv run python -m kri_space_autonomy.assurance_report \
  assess kri_space_autonomy.examples.proportional_controller:controller \
  fault-suites/example-rpo.json assessment-policies/example-rpo.json \
  --json-output reports/example-rpo-assessment.json \
  --markdown-output reports/example-rpo-assessment.md \
  --stdout none
```

The output is evidence from this simplified harness. It is not formal assurance, certification, or a
flight-safety claim. See the [assurance report guide](docs/assurance-report.md).

## Core benchmark CLI

Run one scenario and write a hash-chained evidence log:

```bash
kri-space-lab run scenarios/sensor-dropout.json \
  --controller protected \
  --evidence results/sensor-dropout.jsonl

kri-space-lab verify-evidence results/sensor-dropout.jsonl
```

Compare the built-in controller fixtures across scenarios:

```bash
kri-space-lab benchmark scenarios/*.json --output results/baseline.json
```

Check the bounded safety envelope:

```bash
kri-space-lab verify-gate
```

The gate check is a finite regression property check, not formal reachability analysis.

## Completed confirmatory evidence

The later studies deliberately preserve null and inconclusive outcomes.

- [Experiment 002 final confirmatory](docs/experiment-002-confirmatory.md)
- [Experiment 003 final confirmatory](docs/experiment-003-confirmatory.md)
- [Experiment 004 final result](docs/experiment-004-results.md)
- [Experiment 005 confirmatory design](docs/experiment-005-confirmatory.md)
- [Experiment 005 final closeout](docs/experiment-005-confirmatory-closeout.md)

Experiment 005 completed 1,068 paired blocks and 2,136 episodes. Fixed-cell validity passed and its
prespecified replay was byte-identical. The primary physical-safety test was inconclusive because
both configurations recorded zero physical adverse events; H2 was not formally tested after H1
closed the gate.

## KRI-STD-001 connection

The repository exercises selected concepts around independent runtime assurance, bounded safety
constraints, model identity, fault injection, graceful degradation, and reconstructable evidence.
The mapping now spans the completed experimental programme rather than only the original v0.1
fixture.

See [the detailed KRI-STD-001 mapping](docs/kri-std-001-mapping.md).

KRI-STD-001 v1.3 is available at:
https://www.kri.org.uk/publications/trustworthy-onboard-ai-standard-for-space-systems

## Repository structure

```text
src/kri_space_autonomy/   environment, controllers, adapters, faults, reports and experiment code
scenarios/                reproducible public scenario definitions
fault-suites/             deterministic product-facing fault suites
assessment-policies/      explicit assessment criteria
tests/                    regression, integrity and safety-property tests
docs/                     benchmark guides, experiment records and standard mapping
demo/                     deterministic public JSON/Markdown/HTML bundles
results/                  checked-in benchmark and frozen campaign evidence
```

## Scope and non-claims

The repository contains simplified one-dimensional, planar HCW, and nonlinear central-gravity
research models. It does **not** establish 6-DoF validity, hardware-in-the-loop validity, operational
fault prevalence, flight qualification, certification, or regulatory conformance.

## Citation

Use `CITATION.cff` or cite the stable GitHub release tagged `v0.1.0`. Release notes are in
[`docs/release-v0.1.0.md`](docs/release-v0.1.0.md). Cite KRI-STD-001 separately where its assurance
framework is used.

## Licence

Apache-2.0.
