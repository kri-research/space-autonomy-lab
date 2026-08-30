# Experiment 002c numerical corrective amendment

_Frozen numerical-only replay; Experiments 002 and 002b remain historical_

---

## ✅ Decision

**`pass`**. Numerical blocker resolved: 
`true`.

The operational and rate campaigns were not rerun. The `32,000`-episode
confirmatory campaign and combined-fault study were not run.

## 📊 Numerical replay

- Complete traces: `24`
- Event ordering identical: `true`
- Required classifications identical: `true`
- `braking_unreachable` identical: `true`
- All coarse/fine convergence checks passed: `true`

| Quantity | Production/fine max | Bound | Coarse/fine max | 25% bound |
| --- | ---: | ---: | ---: | ---: |
| achieved_acceleration_mps2 | `4.857e-17` | `1.000e-12` | `3.031e-15` | `2.500e-13` |
| collision_residual_m | `9.459e-13` | `1.000e-10` | `6.661e-16` | `2.500e-11` |
| depletion_residual_fraction | `8.159e-13` | `1.000e-12` | `2.236e-19` | `2.500e-13` |
| dwell_fraction | `0.000e+00` | `1.000e-10` | `0.000e+00` | `2.500e-11` |
| event_time_s | `4.592e-10` | `2.000e-07` | `3.530e-11` | `5.000e-08` |
| propellant_fraction | `1.209e-13` | `1.000e-10` | `1.565e-13` | `2.500e-11` |
| range_m | `4.606e-09` | `1.000e-08` | `6.539e-10` | `2.500e-09` |
| velocity_mps | `1.213e-11` | `1.000e-10` | `1.922e-12` | `2.500e-11` |

## 🔍 Historical diagnosis

The frozen 002b replay remains failed. Independent inspection again found that all
smooth maximum-closing traces passed while reversal/depletion patterns dominated the
error and all required classifications matched. Focused regression tests cover the
separate production terminal-extremum defect.

## 🎯 Next scientific blocker

`combined_fault_nuisance_information_requirement`.
