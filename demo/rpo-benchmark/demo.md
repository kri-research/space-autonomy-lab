# Space Autonomy Lab: deterministic RPO controller demo

A compact, repeatable path from **your controller** to **declared faults** to a **traceable criteria report** in a simplified one-dimensional rendezvous/proximity-operations (RPO) harness.

> **Evidence boundary:** The run below is an illustrative product example, not scientific evidence. The historical results are frozen synthetic-benchmark evidence. Nothing here is a full GNC assessment, formal verification, certification, operational fault-prevalence estimate, or flight-safety claim.

## Try the harness — product example

`controller plugin → public adapter → deterministic fault suite → declared policy → stable report`

- **Result:** `PASS` within the checked-in policy only
- **Controller:** `example.proportional` v`1.0.0`
- **Fault suite:** `example-rpo-faults` · `74c97631f3003431403b060c99076258c68bbf895fff9655fa27f4af72ee0408`
- **Assessment policy:** `example-rpo-acceptance` · `6f20864f87a7070d97a2c96a72293577a33768b7fe0a8e92bd5e2548e59af82e`
- **Harness report fingerprint:** `552b26856976ebc3057fa220f3ab7b48c6f0d93f924cf2f800badcafcff948c9`

| Case | Faults | Role / result | Success | Collision | Final range (m) | Final speed (m/s) | Propellant | Degraded / missing obs. | Actuator-modified |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `nominal` | none | required / **PASS** | True | False | 7.917475 | -0.059786 | 0.999414679 | 0 / 0 | 0 |
| `range-bias` | `biased-range` | required / **PASS** | True | False | 7.892674 | -0.058740 | 0.999413110 | 51 / 0 | 0 |
| `navigation-dropout` | `missing-navigation` | required / **PASS** | True | False | 7.900007 | -0.059049 | 0.997013574 | 16 / 16 | 0 |
| `actuator-degradation` | `reduced-effectiveness` | required / **PASS** | True | False | 7.910090 | -0.059557 | 0.999414335 | 0 / 0 | 33 |
| `dropout-plus-degradation` | `missing-navigation`, `reduced-effectiveness` | informational / **INFORMATIONAL** | True | False | 7.917026 | -0.059767 | 0.998454658 | 16 / 16 | 71 |

A `PASS` here means only that every required example case met the checked-in criteria. The composed case is explicitly informational.

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

- **Demo input fingerprint:** `1c9fbda6409baf7db49b57f5633b76d5ae2c92af53cfe67a44e06968edb56e9b`
- **Demo substantive fingerprint:** `04d23ce0d2a05122cb87ab2bbce65c74b76397b01e0def24bfa6f3d641cc582d`

## Try another controller

Implement the small contract in [`docs/controller-adapter.md`](../../docs/controller-adapter.md), then run:

```bash
uv run python -m kri_space_autonomy.demo build \
  --controller my_controller:controller \
  --output demo/my-controller
```

Open `demo/my-controller/index.html`. The command reuses the same public adapter, fault-suite, and assessment-report APIs.

## Limitations

- Simplified deterministic one-dimensional relative-motion environment; not a full GNC stack.
- Fault cases are declared stress tests, not estimates of operational fault prevalence.
- Local Python controllers run in process and should be trusted code.
- A PASS means only that required cases met the checked-in policy in this harness.
- Frozen Experiment 002 and 003 results have different measurement boundaries.
- No formal verification, certification, hardware, timing, or flight-safety claim is made.

Machine-readable payload: [`demo.json`](demo.json) · Standalone page: [`index.html`](index.html)
