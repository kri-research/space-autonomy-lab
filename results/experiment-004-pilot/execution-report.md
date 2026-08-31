# Experiment 004 planar HCW pilot execution report

_One-time, non-inferential partition-43 design-validation pilot on `experiment-004-pilot-run` at `1415b3490315501bb1a33bc6e51b48347db191f1`._

---

## 📋 Decision summary

All frozen pilot gates passed. The overall frozen decision is `pilot_design_gates_passed`. This is an engineering design-validation result only: no scientific hypothesis was tested, no architecture effect was estimated, and no superiority, noninferiority, multiplicity, or architecture-benefit claim is enabled.

- Materialization: **1 successful invocation**, 44 unique roots in 11 cases, 4 roots per case
- Execution: **1 invocation**, 44 complete blocks, 88 episodes
- Replay: 11 replicate-0 blocks, 22 episodes, byte-identical digest
- Infrastructure: 0 failures (0.0%; frozen maximum 1%)
- Overall QC: pass

## 🔍 Frozen identities and scope

| Identity | Verified value |
| --- | --- |
| Foundation freeze | `54a0f1a8dc985fba02973c09ac994fbc76a2ef1abbc7dfe5def82585c85aaa14` |
| Foundation readiness | `fd0ea450e8b5f53a4447cf3910e7e3b494ed6bace33da0055f64e77fd9049404` |
| Pilot-design freeze | `8f0867a4eaa34c3fb1aef1d8fff62fb579e3099391c5c722b87a3dc6b0746079` |
| Pilot-design readiness | `5c39bbdc231f7355b9afc79387816b604dbca2f16015e0d179b48f77b6d0d809` |
| Partition-43 seed manifest | `bb01acd3426f1e2e5c948cbb3d48c6aa48141ca261cf885c63b6a292f94eff5e` |
| Pilot episode rows | `eb23f9ee42118f91f01d77a2dd55ee5ca9678b2a9eb731a9a57b732b2770bcdc` |

Frozen foundation and pilot-design source hashes had zero mismatches. Experiment 001–003 historical integrity, Experiment 002 final results, Experiment 003 pilot/final results, stable gate, runtime identity, information boundary, privacy scan, compileall, lint, tests, and diff hygiene passed.

## ✅ Gate results

| Frozen gate | Result | Evidence |
| --- | --- | --- |
| Complete cells | Pass | 44/44 blocks; 88/88 episodes; 0 missing, extra, or duplicate cells |
| Forced collision | Pass | 8/8 configured episodes activated collision and keep-out |
| Forced keep-out only | Pass | 8/8 activated keep-out; 0/8 collision |
| Forced corridor only | Pass | 8/8 activated corridor departure; 0/8 collision or keep-out |
| Nominal safe finite hold | Pass | 8/8 acquired hold; dwell range 120.8–134.5 s; no physical hazard |
| Fault/channel activation | Pass | Primary, monitor, monitor-logic, shared, actuation, and disturbance checks all passed separately |
| Covariance/numerical validity | Pass | Minimum covariance eigenvalue 1.21121e-06; maximum covariance trace 50.0101; all finite/valid |
| Information boundary | Pass | No prohibited truth, fault-label, scenario, root, or evaluator inputs found |
| Infrastructure | Pass | 0/88 failures; no retries or replacements |
| Deterministic replay | Pass | 11 blocks/22 episodes; digest `7b630fbdc1e4a3d8971a05d7766b51dc21dff3a41eef2a44e4d1c7d159f70dfa` |

## 📊 Per-case mechanistic findings

Counts below are descriptive activation and event records. Configuration-specific monitor-gate override counts are diagnostics, not comparative effects.

| Case | Domain | Physical/mission observation | Scheduled/mechanistic activation | Gate |
| --- | --- | --- | --- | --- |
| `P00_nominal_feasibility` | Mission feasibility | hold 8/8; collision/keep-out/corridor 0/0/0 | none scheduled; monitor-gate overrides=2 | Pass |
| `P01_forced_collision` | Physical geometry | collision 8/8; keep-out 8/8 | none scheduled; monitor-gate overrides=4 | Pass |
| `P02_forced_keep_out_only` | Physical geometry | keep-out 8/8; collision 0/8 | none scheduled; monitor-gate overrides=4 | Pass |
| `P03_forced_corridor_departure` | Physical geometry | corridor 8/8; collision/keep-out 0/0 | none scheduled; monitor-gate overrides=4 | Pass |
| `P04_primary_navigation_bias` | Primary estimator | hold 8/8; collision/keep-out/corridor 0/0/0 | primary=240; monitor-gate overrides=3 | Pass |
| `P05_primary_navigation_dropout` | Primary estimator | hold 8/8; collision/keep-out/corridor 0/0/0 | primary=48; monitor-gate overrides=2 | Pass |
| `P06_monitor_navigation_bias` | Monitor estimator | hold 8/8; collision/keep-out/corridor 0/0/0 | monitor=240; monitor-gate overrides=121 | Pass |
| `P07_monitor_logic_false_trip` | Monitor logic | hold 8/8; collision/keep-out/corridor 0/0/0 | logic=24; monitor-gate overrides=25 | Pass |
| `P08_shared_navigation_bias` | Shared cause | hold 8/8; collision/keep-out/corridor 0/0/0 | primary=240, monitor=240; monitor-gate overrides=123 | Pass |
| `P09_actuation_degradation` | Actuation | keep-out 8/8; hold 0/8; collision 0/8 | actuation=480; monitor-gate overrides=916 | Pass |
| `P10_disturbance_burst` | Disturbance | corridor 8/8; hold 0/8; collision/keep-out 0/0 | disturbance=1920; monitor-gate overrides=804 | Pass |

Physical hazards, mission performance, primary-estimator faults, monitor-estimator faults, monitor-logic faults, shared-cause faults, actuation degradation, disturbance, and infrastructure failure remained separately recorded in every episode row.

## 🔄 Reproducibility

The prespecified same-platform replay selected replicate 0 in every case. Original and replayed 22-episode canonical digests were both `7b630fbdc1e4a3d8971a05d7766b51dc21dff3a41eef2a44e4d1c7d159f70dfa`. Runtime matched the frozen platform: CPython 3.11.16, NumPy 2.4.6, SciPy 1.17.0, Darwin arm64, with the frozen dependency-file hashes and no configured thread variables.

Exactly-once evidence is recorded in `execution-ledger.json`. Materialization and result paths are write-once, root and cell uniqueness checks passed, and no retry, replacement, or extension was observed.

## ⚠️ Issues and limitations

- No pilot gate or infrastructure issue was observed.
- The frozen CLI's pre-materialization freeze verifier is intentionally phase-inapplicable after partition 43 exists. Frozen source was not edited; execution used the frozen seed validator and runner directly, and post-execution integrity used frozen hashes plus phase-appropriate checks.
- The model remains a local planar linear circular-orbit HCW approximation. It excludes nonlinear and three-dimensional orbital mechanics, attitude, plume/contact dynamics, broader timing jitter, flight software, hardware-in-the-loop, operational validation, and flight-safety claims.
- Eleven cases and four roots per case were selected for mechanics validation, not statistical power. These results do not estimate operational frequencies or architecture benefit.

## 🎯 Next task boundary

Because all pilot design-validation gates passed, the next task—if the program elects to continue—should be a **separate prospective confirmatory-design freeze**. It must define its own hypothesis, estimand, sample size, analysis, and write-once partition-44 mechanism before any confirmatory outcomes. Partition 44 remains reserved, unmaterialized, without a generator, hypothesis, or sample size. No confirmatory design was created or enabled here.

## 📦 Durable artifacts

- Seeds: `experiments/004-pilot/seeds/`
- Episodes and execution: `results/experiment-004-pilot/pilot-episodes.jsonl`, `execution-summary.json`
- Analysis and QC: `analysis.json`, `qc.json`
- Integrity and reproducibility: `design-integrity-postexecution.json`, `reproducibility.json`
- Validation and ledger: `phase-validation.json`, `result-verification.json`, `execution-ledger.json`
- Final inventory and checksums: `manifest.json`, `checksums.sha256`
