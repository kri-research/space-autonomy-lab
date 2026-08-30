# Public deterministic RPO demo

This demo is the shortest path through Space Autonomy Lab for an external spacecraft/autonomy
engineer. It exercises an importable controller against declared, deterministic observation and
actuator faults, applies an explicit assessment policy, and emits portable evidence files.

> **Scope:** a simplified one-dimensional rendezvous/proximity-operations controller test harness.
> It is not a full guidance, navigation, and control stack, a simulator of record, formal
> verification, certification, or flight-safety evidence.

## Build and view

From the repository root:

```bash
uv sync --frozen --extra dev
uv run python -m kri_space_autonomy.demo build --open
```

Without `--open`, view `demo/rpo-benchmark/index.html` directly with a browser. It works from
directly from disk and has no external JavaScript, CSS, font, or network dependency.

The build writes:

| File | Purpose |
| --- | --- |
| `demo/rpo-benchmark/index.html` | Standalone visual walkthrough |
| `demo/rpo-benchmark/demo.md` | Concise, diff-friendly walkthrough |
| `demo/rpo-benchmark/demo.json` | Stable machine-readable payload |
| `demo/rpo-benchmark/bundle-manifest.json` | Input/demo fingerprints plus file SHA-256 identities |

No timestamps or local absolute paths enter the substantive payload or its fingerprints.

## What runs

The **Try the harness** layer is a product example, not a scientific campaign:

```text
external controller
  → public controller adapter
  → checked-in deterministic fault suite
  → checked-in assessment policy
  → stable report
```

The default build uses:

- controller: `kri_space_autonomy.examples.proportional_controller:controller`
- suite: `fault-suites/example-rpo.json`
- policy: `assessment-policies/example-rpo.json`

The demo generator calls the existing assessment-report API. That API performs exact replay through
the existing fault-suite and controller-adapter APIs. The demo does not copy or redefine simulator,
fault, evaluator, or report semantics.

A harness `PASS` means only that every required example case met the checked-in criteria. It does not
establish assurance or safety outside this harness. The composed dropout-plus-actuator case is
informational by policy.

## Try your controller

Implement the observation/command lifecycle in the [controller adapter guide](controller-adapter.md),
then run:

```bash
uv run python -m kri_space_autonomy.demo build \
  --controller my_controller:controller \
  --output demo/my-controller
```

Open `demo/my-controller/index.html`. The controller receives only the public
`ControllerObservation` fields documented in the adapter contract. It does not receive simulator
truth, achieved actuation, fault labels/schedules, evaluator state, or case metadata. Local Python
plugins run in process, so load only trusted controller code.

## Frozen architecture evidence

The second layer is read-only historical evidence. The build does **not** rerun either campaign. For
each campaign it reads the complete final aggregate `analysis.json`, verifies its SHA-256 against the
frozen run manifest and `SHA256SUMS`, and checks the matching freeze ID. It does not read or select
historical roots or episode records.

| Campaign | Measurement boundary | Frozen result |
| --- | --- | --- |
| Experiment 002 final confirmatory | Direct measurements; simplified 1-D synthetic benchmark | **Favorable** under its frozen serial gates: H1 PD-D analysis-hazard risk difference `-0.04125`, 95% interval `[-0.045, -0.037625]`; H2 tested and passed. |
| Experiment 003 final confirmatory | Estimator in the loop; simplified 1-D synthetic benchmark | **Inconclusive**. D and PD had zero analysis-hazard risk in every E0-E6 stratum, so H1 PD-D was `0` with 95% interval `[0, 0]` and did not pass. H2 was not tested because the serial gate closed. |

Experiment 003's sustained-success PD-D estimate of `-0.184` is descriptive because H2 was not
tested. The complete stratum summary is rendered in the bundle; the negative result was concentrated
in monitor-range-bias E5 (`-0.689333…`) and shared-range-bias E6 (`-0.633333…`). This campaign did
not confirm a safety advantage.

The direct-measurement and estimator-in-loop results have different evidence boundaries. Do not
combine them into one architecture claim or treat either as operational fault prevalence,
certification, or flight-safety evidence.

## Deterministic identity

`demo.json` contains:

- controller contract, version, and module-source identity;
- fault-suite result and suite identities;
- assessment-policy and report identities;
- each frozen campaign's freeze ID and complete aggregate result hash;
- an input fingerprint over those identities;
- a substantive demo fingerprint over the complete timestamp-free payload.

`bundle-manifest.json` adds SHA-256 and byte length for the generated JSON, Markdown, and HTML. Two
builds from the same repository/controller state are byte-identical.
