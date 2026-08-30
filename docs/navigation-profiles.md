# Product navigation profiles

The product harness supports the same external controller import specification through two
navigation profiles:

- `direct` — the existing product behavior and default;
- `estimated` — a thin bridge around the frozen Experiment 003 **primary** navigation filter.

The estimated profile is an illustrative engineering stress-test capability. Runs made through it
are not Experiment 003 reruns, new scientific evidence, hypothesis tests, or estimates of
operational fault prevalence.

## One controller, two workflows

```bash
CONTROLLER=kri_space_autonomy.examples.proportional_controller:controller

uv run python -m kri_space_autonomy.controller_adapter \
  replay "$CONTROLLER" scenarios/nominal.json \
  --navigation-profile direct

uv run python -m kri_space_autonomy.controller_adapter \
  replay "$CONTROLLER" scenarios/nominal.json \
  --navigation-profile estimated
```

The controller contract remains version `1.0`. No field was added. Both profiles deliver exactly one
`ControllerObservation` containing:

| Field | Unit / semantics |
| --- | --- |
| `step` | Non-negative command-step index |
| `time_s` | Seconds; exactly `step × command_period_s` |
| `range_m` | Metres; direct observation or estimated range; optional only on fail-closed missing output |
| `relative_velocity_mps` | Metres per second; negative means closing; optional only on fail-closed missing output |
| `propellant_fraction` | Unitless fraction in `[0, 1]` |
| `sensor_quality` | Unitless deterministic status encoding in `[0, 1]` |

The controller never receives simulator truth, realized process disturbance, achieved actuation,
fault labels or schedules, evaluator output, estimator covariance, innovation values, offline truth
error, or NEES. Plugins execute locally in process and should be trusted code.

## Estimated lifecycle

For each command step, the bridge performs this deterministic sequence:

1. For steps after zero, advance the frozen filter to the current epoch using the **previous
   requested controller command**. The post-fault actuator action is not fed back to the filter.
2. Apply the existing product fault pipeline to the raw product observation.
3. If range and velocity are present, call the frozen Experiment 003 `navigation_packet` factory
   with zero added random noise, the frozen quantization, the frozen nominal measurement covariance,
   and equal measurement/receipt epochs. If both fields are missing, perform prediction only.
4. Ingest the packet through the frozen `NavigationFilter`, including its timestamp, duplicate,
   fixed-lag, innovation-rejection, Joseph covariance-update, and divergence handling.
5. Reuse the frozen `policy_observation` mapping, then translate it into the unchanged public
   `ControllerObservation`.
6. Validate the controller command through the existing adapter. Save that requested command for
   the next prediction. Only afterward may the product fault pipeline modify plant actuation.

Range and velocity must be present together. Non-finite values, malformed packet plans, timing
mismatch, asset/hash drift, command-period mismatch, and initial states outside the frozen estimator
limits abort the run. The bridge never silently switches back to direct measurements.

## Health and public status mapping

The mapping is the frozen Experiment 003 mapping; it is not tuned for this product milestone.

| Frozen filter state | Public values | `sensor_quality` | Public status |
| --- | --- | ---: | --- |
| `valid` | Estimated range and velocity | `1.0` | `nominal` |
| `degraded`, accepted-measurement age ≤ 2 s | Estimated range and velocity | `0.7` | `degraded` |
| `degraded`, no accepted measurement or age > 2 s | Estimated range and velocity | `0.4` | `degraded` |
| `diverged` | Range and velocity are `None` | `0.0` | `missing` |

A missing raw packet does not cause truth fill. The filter predicts. With a previously accepted
packet it remains valid through prediction-only ages 1 s and 2 s, then becomes degraded after the
frozen `2.0 s` threshold. A stale duplicate or rejected innovation degrades the filter immediately.
Numerical divergence is latched by the frozen filter and maps to missing navigation predictably.

## Exact frozen identity and explicit bridge boundary

At estimated-profile startup, the product facade reads
`experiments/003/freeze-manifest.json`, requires foundation freeze ID
`d032ed6b22ff3bb74bc5b03caf2b287a8310b16eb8d76665020a66d98eab2297`, and verifies the
recorded raw-byte SHA-256 values for:

- `experiments/003/config.json`;
- `experiments/002/config.json`;
- Experiment 002 configuration source;
- Experiment 003 configuration, estimator, interface, measurement, and model source.

The frozen estimator configuration SHA-256 is
`e83f59a5c3c86defab150285b1dc30d170b08f82c8f949a348944efe5963b4c9`; the frozen estimator
source SHA-256 is
`3502d00eef9a4a34417775ca1e20fc609a2726797c7a30ddb564d5fc58a3d481`. The product identity
also hashes the complete verified file map and explicit bridge description.

The models are intentionally not identical. The product `simplified-rpo-v1` plant applies
acceleration instantaneously at 1 s steps. The frozen estimator retains Experiment 003's first-order
actuator state (`0.5 s` time constant), process covariance derived from `0.25 s` disturbance
intervals, and frozen thresholds/covariances. The bridge feeds requested commands and product
measurements without changing either side. Product results therefore combine navigation stress with
this disclosed model boundary and must not be described as an Experiment 003 replication.

## Illustrative estimator fault examples

The small estimated example set is separate from the seven scientific Experiment 003 strata:

```bash
uv run python -m kri_space_autonomy.fault_suite \
  validate fault-suites/example-estimated-rpo.json

uv run python -m kri_space_autonomy.fault_suite \
  validate-navigation-plan navigation-fault-plans/example-estimated-rpo.json

uv run python -m kri_space_autonomy.fault_suite \
  replay-suite kri_space_autonomy.examples.proportional_controller:controller \
  fault-suites/example-estimated-rpo.json \
  --navigation-profile estimated \
  --navigation-fault-plan navigation-fault-plans/example-estimated-rpo.json
```

The base suite reuses existing inclusive-window product semantics for range bias and navigation
dropout. The separately versioned and suite-hash-bound navigation plan adds only:

- `stale_packet` — reuses the frozen packet factory's prior sequence ID and source epoch, causing the
  frozen filter to reject a duplicate;
- `covariance_underreporting` — uses the frozen factor `0.25`; the plan cannot supply or tune a
  factor.

The product architecture has one primary estimator. It does not claim an independent monitor or a
shared-channel architecture, so monitor-only and shared-channel faults are deliberately absent.
No randomized measurement noise or latency is added to these examples.

## Result and report boundaries

Direct results remain `kri-fault-suite-result/1.0` and are byte-compatible with the previous default.
Estimated results use `kri-fault-suite-result/1.1` and bind the navigation profile identity, optional
packet-fault-plan identity, per-case navigation trace, and counts for:

- raw and controller-delivered observation status;
- estimator health and reason;
- accepted, innovation-rejected, duplicate, missing, old, future, invalid, and diverged packet
  dispositions;
- final estimator health, prediction-only age, accepted updates, rejections, and invalid packets.

Direct assurance reports remain `kri-assurance-report/1.0`; estimated reports use
`kri-assurance-report/1.1`. Estimated reports label controller-input summaries, report-only
navigation diagnostics, and truth-derived harness evaluator outputs separately. Success, collision,
final range/speed, and final propellant may still be used for simulation scoring, but they are never
controller inputs. Offline truth-error and NEES metrics are not included in product reports. The
complete canonical packet-fault plan is embedded and revalidated so offline reports can verify its
suite binding, identity, and per-case mapping.

## Public demo

```bash
uv run python -m kri_space_autonomy.demo build --navigation-profile estimated --open
```

This writes `demo/rpo-estimated/` by default. The product layer is illustrative. The frozen Experiment
002 and Experiment 003 aggregate evidence remains a separate read-only layer; Experiment 003's final
confirmatory result remains inconclusive.
