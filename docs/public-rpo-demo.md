# Public deterministic RPO demo

This demo is the shortest path through Space Autonomy Lab for an external spacecraft/autonomy
engineer. It exercises an importable controller against declared deterministic observation and
actuator faults, applies an explicit assessment policy, and emits portable evidence files.

> **Scope:** a simplified one-dimensional rendezvous/proximity-operations controller test harness.
> It is not a full guidance, navigation, and control stack, a simulator of record, formal
> verification, certification, or flight-safety evidence.

## Build and view

From the repository root:

```bash
uv sync --frozen --extra dev
uv run python -m kri_space_autonomy.demo build --open

# Same controller through the frozen-estimator product profile.
uv run python -m kri_space_autonomy.demo build \
  --navigation-profile estimated --open
```

Without `--open`, view `demo/rpo-benchmark/index.html` for the direct profile or
`demo/rpo-estimated/index.html` for the estimated profile. Each works directly from disk and has no
external JavaScript, CSS, font, or network dependency.

The direct build writes:

| File | Purpose |
| --- | --- |
| `demo/rpo-benchmark/index.html` | Standalone visual walkthrough |
| `demo/rpo-benchmark/demo.md` | Concise, diff-friendly walkthrough |
| `demo/rpo-benchmark/demo.json` | Stable machine-readable payload |
| `demo/rpo-benchmark/bundle-manifest.json` | Input/demo fingerprints plus file SHA-256 identities |

The estimated bundle uses the same four filenames under `demo/rpo-estimated/`. No timestamps or
local absolute paths enter either substantive payload or its fingerprints.

## What runs

The **Try the harness** layer is a product example, not a scientific campaign:

```text
external controller
  -> public controller adapter
  -> checked-in deterministic fault suite
  -> checked-in assessment policy
  -> stable report
```

The default direct build uses:

- controller: `kri_space_autonomy.examples.proportional_controller:controller`
- suite: `fault-suites/example-rpo.json`
- policy: `assessment-policies/example-rpo.json`

The estimated build uses the same controller spec with
`fault-suites/example-estimated-rpo.json`, its suite-bound navigation fault plan, and
`assessment-policies/example-estimated-rpo.json`. It imports the frozen Experiment 003 primary
filter without retuning it. Its output is an illustrative engineering stress run, not new scientific
evidence. Exact lifecycle, status, identity, and model-boundary semantics are in the
[navigation profile guide](navigation-profiles.md).

The demo generator calls the existing assessment-report API. That API performs exact replay through
the existing fault-suite and controller-adapter APIs. The demo does not copy or redefine simulator,
fault, evaluator, or report semantics.

A harness `PASS` means only that every required example case met the checked-in criteria. It does not
establish assurance or safety outside this harness. In the direct example, the composed
dropout-plus-actuator case is informational by policy.

## Try your controller

Implement the observation/command lifecycle in the [controller adapter guide](controller-adapter.md),
then run:

```bash
uv run python -m kri_space_autonomy.demo build \
  --controller my_controller:controller \
  --output demo/my-controller

uv run python -m kri_space_autonomy.demo build \
  --navigation-profile estimated \
  --controller my_controller:controller \
  --output demo/my-estimated-controller
```

Open `demo/my-controller/index.html`. The controller receives only the public
`ControllerObservation` fields documented in the adapter contract. It does not receive simulator
truth, achieved actuation, fault labels/schedules, evaluator state, or case metadata. Local Python
plugins run in process, so load only trusted controller code.

## Frozen evidence embedded in the demo

The second layer is read-only historical evidence. The build does **not** rerun a scientific
campaign. It reads complete final aggregate artifacts, verifies their stored identities, and does not
select historical roots or episode records.

The current visual demo embeds Experiments 002 and 003 because both share the simplified
one-dimensional product-harness boundary:

| Campaign | Measurement boundary | Frozen result |
| --- | --- | --- |
| Experiment 002 final confirmatory | Direct measurements; simplified 1-D synthetic benchmark | **Favorable** under its frozen serial gates: H1 PD-D analysis-hazard risk difference `-0.04125`, 95% interval `[-0.045, -0.037625]`; H2 tested and passed. |
| Experiment 003 final confirmatory | Estimator in the loop; simplified 1-D synthetic benchmark | **Inconclusive**. D and PD had zero analysis-hazard risk in every E0-E6 stratum, so H1 PD-D was `0` with 95% interval `[0, 0]` and did not pass. H2 was not tested because the serial gate closed. |

Experiment 003's sustained-success PD-D estimate of `-0.184` is descriptive because H2 was not
tested. The complete stratum summary is rendered in the bundle; the negative descriptive effect was
concentrated in monitor-range-bias E5 (`-0.689333...`) and shared-range-bias E6 (`-0.633333...`).
This campaign did not confirm a safety advantage.

## Later programme evidence

Experiments 004 and 005 deliberately sit outside the embedded one-dimensional demo because they use
stronger dynamics and different physical-evaluation boundaries. They are part of the Space Autonomy
Lab benchmark programme, but their results should not be merged into the same demo-level architecture
claim.

| Campaign | Dynamics / evidence boundary | Frozen result |
| --- | --- | --- |
| Experiment 004 final confirmatory | Planar HCW dynamics; independent physical adverse-event endpoint | **Valid, reproducible, inconclusive.** The valid replacement campaign completed 1,452 paired blocks / 2,904 episodes; both configurations had zero physical adverse events in the 1,068 primary paired roots. |
| Experiment 005 final confirmatory | Nonlinear central-gravity truth with model mismatch | **Valid, reproducible, inconclusive.** 1,068 paired blocks / 2,136 episodes; fixed-cell validity passed; replay byte-identical; both configurations had zero physical adverse events. |

See [Experiment 004 final result](experiment-004-results.md),
[Experiment 005 final closeout](experiment-005-confirmatory-closeout.md), and the
[benchmark guide](benchmark-guide.md).

The evidence boundaries differ. Do not pool these campaigns into one effect estimate or treat any of
them as operational fault prevalence, certification, or flight-safety evidence.

## Deterministic identity

`demo.json` contains:

- controller contract, version, and module-source identity;
- fault-suite result and suite identities;
- assessment-policy and report identities;
- the embedded frozen campaigns' freeze IDs and complete aggregate result hashes;
- an input fingerprint over those identities;
- a substantive demo fingerprint over the complete timestamp-free payload.

`bundle-manifest.json` adds SHA-256 and byte length for the generated JSON, Markdown, and HTML. Two
builds from the same repository/controller state are byte-identical.

The later Experiment 004/005 records remain separate frozen research artifacts and are linked rather
than copied into the one-dimensional demo payload.
