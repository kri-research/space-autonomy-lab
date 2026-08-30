# Space Autonomy Lab: estimated-navigation RPO controller demo

A compact, repeatable path from **your controller** to **declared faults** to a **traceable criteria report** in a simplified one-dimensional rendezvous/proximity-operations (RPO) harness.

> **Evidence boundary:** The run below is an illustrative product example, not scientific evidence. The historical results are frozen synthetic-benchmark evidence. Nothing here is a full GNC assessment, formal verification, certification, operational fault-prevalence estimate, or flight-safety claim.

## Try the harness — product example

`controller plugin → public adapter → deterministic fault suite → declared policy → stable report`

- **Result:** `PASS` within the checked-in policy only
- **Controller:** `example.proportional` v`1.0.0`
- **Fault suite:** `example-estimated-rpo-faults` · `d2942ef8a80249e201f7c8733de3ed2d124da2457362e0e5e08e781752264882`
- **Assessment policy:** `example-estimated-rpo-acceptance` · `a687128cfd053adfc85b3d889600f850d9d43f574e069f2efd85bb20382f5ada`
- **Navigation profile:** `estimated` · `c3ac7126041916d6d6d334dbec14513757c90624bb2e6701f778084c400af209`
- **Frozen estimator foundation:** `d032ed6b22ff3bb74bc5b03caf2b287a8310b16eb8d76665020a66d98eab2297`
- **Harness report fingerprint:** `e7c30e80b2811cf85be7a6df8fc3f62d80e6a1913f4443d3f3082bfcb189f464`

| Case | Faults | Role / result | Success | Collision | Final range (m) | Final speed (m/s) | Propellant | Degraded / missing obs. | Actuator-modified |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `nominal` | none | required / **PASS** | True | False | 7.883532 | -0.059050 | 0.999371503 | 0 / 0 | 0 |
| `range-bias` | `biased-range` | required / **PASS** | True | False | 7.904205 | -0.059733 | 0.999373561 | 51 / 0 | 0 |
| `navigation-dropout` | `missing-navigation` | required / **PASS** | True | False | 7.881739 | -0.058989 | 0.999371595 | 14 / 0 | 0 |
| `stale-packet` | none | required / **PASS** | True | False | 7.883508 | -0.058865 | 0.999371491 | 16 / 0 | 0 |
| `biased-covariance-underreporting` | `biased-range` | required / **PASS** | True | False | 7.881746 | -0.058915 | 0.999371449 | 21 / 0 | 0 |

### Estimated navigation diagnostics

Packet dispositions and estimator health are harness diagnostics, not controller inputs. Success, collision, and final state remain truth-derived evaluator outputs. Offline truth error and NEES are not reported.

| Case | Final health / reason | Accepted / rejected / invalid | Missing packets | Delivered nominal / degraded / missing |
| --- | --- | ---: | ---: | ---: |
| `nominal` | valid / none | 328 / 0 / 0 | 0 | 328 / 0 / 0 |
| `range-bias` | valid / none | 277 / 51 / 0 | 0 | 277 / 51 / 0 |
| `navigation-dropout` | valid / none | 312 / 0 / 0 | 16 | 314 / 14 / 0 |
| `stale-packet` | valid / none | 312 / 0 / 16 | 0 | 312 / 16 / 0 |
| `biased-covariance-underreporting` | valid / none | 307 / 21 / 0 | 0 | 307 / 21 / 0 |

A `PASS` here means only that every required estimated-profile example met the checked-in criteria. This illustrative result is not scientific evidence.

## Frozen architecture evidence — keep the boundaries separate

Both rows below come from each campaign's **complete frozen aggregate** `analysis.json`; no historical root or episode was selected. The campaigns must not be combined into one architecture or safety claim.

| Campaign | Measurement boundary | Frozen decision | H1: PD-D analysis-hazard RD (95% interval) | H2: PD-D sustained-success RD |
| --- | --- | --- | --- | --- |
| **Experiment 002 final confirmatory** | Direct measurements in the simplified one-dimensional synthetic benchmark. | **favorable** | -0.041250 [-0.045000, -0.037625]; passed `True` | 0.029250; tested; passed `True` |
| **Experiment 003 final confirmatory** | Estimator in the loop in the simplified one-dimensional synthetic benchmark. | **inconclusive** | 0.000000 [0.000000, 0.000000]; passed `False` | -0.184000; not_tested_gate_closed; passed `None` |

- **Experiment 002 final confirmatory:** Favorable under the frozen serial gates in this direct-measurement benchmark. This does not establish the same result with navigation estimation in the loop.
- **Experiment 003 final confirmatory:** Inconclusive. H1 did not pass because D and PD each had zero analysis-hazard risk in every E0-E6 stratum, giving PD-D = 0 with 95% interval [0, 0]. H2 was not tested under the serial gate. Its descriptive sustained-success estimate was strongly negative overall and concentrated in E5/E6.

### Experiment 003 descriptive sustained-success contrast by stratum

H2 was **not tested** because H1 closed the serial gate. These complete per-stratum aggregate PD-D estimates are descriptive; E5/E6 contain the observed degradation.

| Stratum | PD-D sustained-success risk difference |
| --- | ---: |
| `E0_nominal` | 0.006667 |
| `E1_primary_range_bias` | 0.010667 |
| `E2_primary_dropout` | 0.004000 |
| `E3_primary_stale` | 0.004000 |
| `E4_primary_covariance_underreporting` | 0.009333 |
| `E5_monitor_range_bias` | -0.689333 |
| `E6_shared_range_bias` | -0.633333 |

## Traceability

| Campaign | Freeze ID | Aggregate result SHA-256 | Complete aggregate source |
| --- | --- | --- | --- |
| Experiment 002 final confirmatory | `15eb6b3b552e130f7b983930fda10d7d1c0841943408ec8586b51619d9076c15` | `f59cebb40562e8af7c28a0ca39b56744d155a994b07c422935e0d18731f14898` | `results/experiment-002-confirmatory/analysis.json` |
| Experiment 003 final confirmatory | `61d9f5b9657875b24759b4cad8eb83f60a655c09ef68d6892c49731887d505e6` | `daec0cd91683c709d4a56b06846ec96c025ec097030ad292c7dc481aec576516` | `results/experiment-003-confirmatory/analysis.json` |

- **Demo input fingerprint:** `502708c30f852db40e0a08f2ee4fc34221cee3d00ce7308dd75cc8cd49f26aef`
- **Demo substantive fingerprint:** `8dabf19bb7d40d0ad97efd3980c118d12f1755ed40e8bfb5762040b3f98c61df`

## Try another controller

Implement the small contract in [`docs/controller-adapter.md`](../../docs/controller-adapter.md), then run:

```bash
uv run python -m kri_space_autonomy.demo build \
  --navigation-profile estimated \
  --controller my_controller:controller \
  --output demo/my-estimated-controller
```

Open `demo/my-estimated-controller/index.html`. The command reuses the same public adapter, frozen-estimator bridge, illustrative fault set, and assessment-report APIs.

## Limitations

- Simplified deterministic one-dimensional relative-motion environment; not a full GNC stack.
- Fault cases are declared stress tests, not estimates of operational fault prevalence.
- Local Python controllers run in process and should be trusted code.
- A PASS means only that required cases met the checked-in policy in this harness.
- Frozen Experiment 002 and 003 results have different measurement boundaries.
- The estimated product profile reuses the frozen Experiment 003 estimator without retuning on a different instantaneous-actuation product plant.
- Estimator health and packet diagnostics are harness outputs, while success, collision, and final state remain truth-derived evaluator outputs.
- No formal verification, certification, hardware, timing, or flight-safety claim is made.

Machine-readable payload: [`demo.json`](demo.json) · Standalone page: [`index.html`](index.html)
