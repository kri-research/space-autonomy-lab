# Experiment 002 design-validation pilot

_Frozen six-stratum feasibility pilot completed on 2026-08-29_

---

> ⚠️ **Evidence boundary:** These are feasibility/design-validation estimates for the frozen synthetic generator. They are not confirmatory superiority or flight-safety evidence.

## 📋 Campaign

- Complete paired blocks: 2,400 / 2,400
- Episode records: 9,600 / 9,600
- Fixed weights: `1/6` per stratum
- Mixed navigation strata: exactly 200 bias and 200 dropout blocks each
- Paired bootstrap: 50,000 within-stratum block replicates
- Controller or numerical failures: 0

## 📊 Arm outcomes by stratum

| Stratum | Arm | Hazard | Success | Collision | Median fallback duty |
| --- | ---: | ---: | ---: | ---: | ---: |
| `P0` nominal | `R` | 0.000 | 0.998 | 0.000 | 0.000 |
| `P0` nominal | `D` | 0.000 | 0.790 | 0.000 | 0.000 |
| `P0` nominal | `PS` | 0.000 | 0.790 | 0.000 | 0.000 |
| `P0` nominal | `PD` | 0.000 | 0.790 | 0.000 | 0.000 |
| `P1` primary navigation | `R` | 0.117 | 0.877 | 0.117 | 0.000 |
| `P1` primary navigation | `D` | 0.003 | 0.282 | 0.003 | 0.000 |
| `P1` primary navigation | `PS` | 0.000 | 0.200 | 0.000 | 0.012 |
| `P1` primary navigation | `PD` | 0.000 | 0.300 | 0.000 | 0.012 |
| `P2` monitor-only | `R` | 0.000 | 1.000 | 0.000 | 0.000 |
| `P2` monitor-only | `D` | 0.000 | 0.807 | 0.000 | 0.000 |
| `P2` monitor-only | `PS` | 0.000 | 0.807 | 0.000 | 0.000 |
| `P2` monitor-only | `PD` | 0.000 | 0.445 | 0.000 | 0.015 |
| `P3` shared cause | `R` | 0.095 | 0.905 | 0.095 | 0.000 |
| `P3` shared cause | `D` | 0.000 | 0.568 | 0.000 | 0.000 |
| `P3` shared cause | `PS` | 0.000 | 0.400 | 0.000 | 0.008 |
| `P3` shared cause | `PD` | 0.000 | 0.400 | 0.000 | 0.008 |
| `P4` model upset | `R` | 0.000 | 1.000 | 0.000 | 0.000 |
| `P4` model upset | `D` | 0.292 | 0.287 | 0.230 | 0.000 |
| `P4` model upset | `PS` | 0.000 | 1.000 | 0.000 | 0.652 |
| `P4` model upset | `PD` | 0.000 | 1.000 | 0.000 | 0.652 |
| `P5` actuator degradation | `R` | 0.000 | 0.995 | 0.000 | 0.000 |
| `P5` actuator degradation | `D` | 0.000 | 0.812 | 0.000 | 0.000 |
| `P5` actuator degradation | `PS` | 0.000 | 0.812 | 0.000 | 0.000 |
| `P5` actuator degradation | `PD` | 0.000 | 0.812 | 0.000 | 0.000 |

## 🔍 Prespecified paired estimates

For `PD − D`, standardized analysis-hazard risk difference was **−0.0492** with an estimation-only 95% paired-bootstrap interval from `−0.0567` to `−0.0417`. Sustained-success risk difference was **+0.0333** with an estimation-only interval from `+0.0188` to `+0.0475`.

The apparent safety signal was concentrated in persistent model upset: 117 `D`-hazard/`PD`-nonhazard discordant blocks occurred in `P4`, with one more in `P1`; the other four strata had no hazard discordance. `PD` and `PS` had no hazard discordance in any stratum, so the independent-channel safety increment was not estimable from observed hazard events.

Mission effects were heterogeneous. Relative to `D`, `PD` success changed by `+1.75` points in `P1`, `−36.25` points in `P2`, `−16.75` points in `P3`, `+71.25` points in `P4`, and zero in `P0/P5`. The standardized `PD − PS` success difference was `−4.375` points, driven by monitor-only harm despite a `+10`-point independent-channel increment in the primary-navigation mixture.

## ✅ Validation status

| Gate | Status | Evidence |
| --- | --- | --- |
| Locked tests, lint, dependencies, and privacy scan | Pass | 28 tests; zero scan matches |
| Expected cells and completeness | Pass | 2,400 complete blocks; 9,600 unique cells |
| Seed count, mixtures, and scenario hashes | Pass | 400/stratum; exact 200/200; zero drift |
| Same-platform replay | Pass | 960 / 960 episodes reproduced |
| Numerical propagation | Pass | Maximum exact-versus-RK4 error `8.39e-12` |
| Command-rate sensitivity | **Fail** | Classification and continuous-metric thresholds exceeded |
| Confirmatory information gate | **Fail** | Omitted combined-fault nuisance model not approved |

The separate command-rate study compared 1-second results with 0.5- and 0.25-second controller periods over 40 frozen blocks per stratum. It found classification changes, maximum minimum-range change of `1.111 m`, and maximum absolute propellant-use change of `0.283` initial-fraction units. These are controller-rate effects, not numerical integration error.

## ⚠️ Decision and caveats

Progression classification is **`do_not_proceed`** because the command-rate validity gate failed. Even after that defect is resolved, the information gate remains incomplete because this pilot cannot supply nuisance behavior for the omitted combined-fault confirmatory stratum.

The pooled favorable effect direction cannot rescue either failed gate. Results are also sensitive to the six-stratum stress-test weights, the primary learned artifact, the calibrated recovery corridor, and the simplified one-dimensional dynamics. The full eight-stratum, 32,000-episode confirmatory campaign was not run.

Detailed episode records, all contrasts, discordance counts, recovery states, planning simulations, QC failures, manifests, and checksums are available in the adjacent machine-readable artifacts.
