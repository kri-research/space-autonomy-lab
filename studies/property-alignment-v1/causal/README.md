# Controlled predicate experiment

This is an additive developmental mechanistic study, separate from the historical campaigns and from any future frozen evaluation. `protocol.json` fixes the selected cases, complete matrix, endpoints and failure handling before new outcomes. `seal.json` binds its code, property and historical component identities.

The core factorial comparison varies physical plant and online position predicate. Both controlled predicate arms use the same interval Taylor prediction and traversal, while retaining the original controller, one-second horizon, covariance-radius convention and LQR fallback. The original gate is an additional unchanged implementation reference; the no-gate arm still retains estimator safeguards.

All new cells use the independent Task 03 offline property and interval adjudicator. Its validated labels concern the intended mathematical model under exact recorded applied inputs. They do not certify exact numerical feedback equivalence or physical spacecraft safety. Approximate simulator discrepancies and unresolved intervals are retained separately.

Three main ideal initial states are qualified using predeclared, independently enclosed fixed-input continuations. These are finite-horizon existence witnesses, not tuned protective baselines. An outward-moving boundary state is analytically unrecoverable and remains a labelled control. No robust recovery certificate is inferred for noisy estimator cases.

## Execution

Run from `studies/property-alignment-v1` in the existing pinned environment with `SAL_EVIDENCE_ROOT` pointing to the separate historical checkout. Set `OPENBLAS_NUM_THREADS=1` and `PYTHONDONTWRITEBYTECODE=1`.

```sh
python -m pytest tests/test_causal.py
python -m causal.execute verify
python -m causal.execute run --output /path/to/fresh-execution --workers 4
python -m causal.analyze --execution /path/to/fresh-execution --output /path/to/fresh-analysis
```

Execution requires a new directory outside both repositories and never retries or replaces a selected case automatically. Full state, command, packet, input, interval and cost records are retained. Timestamps and a public protocol commit document prospective declaration; they are not external preregistration.

## Interpretation

With identical ideal primary and monitor snapshots, the original LQR fallback computes exactly the proposed command. An aligned rejection can therefore change the log without changing the selected control. This implementation identity is tested; it is not attributed to every noisy case or to other recovery controllers.

The estimator contexts pair innovations, not observation values: each channel's packet is rebuilt from its own arm's motion. Fault injection, packet acceptance, branch evaluation, rejection and command changes are separate recorded events. No significance test, operational prevalence estimate, new assurance theorem or broadly effective recovery method is claimed.

## Recorded result and interpretation limits

`recorded_analysis/RESULTS.md` is the compact result note. `recorded_execution/` retains all 56 selected cells and six feasibility continuations; `recorded_analysis/` retains the complete contrasts and interactions. The source protocol and execution's sorted-key protocol copy are semantically identical but have different byte hashes, both recorded in `artifact_bindings.json`.

The controlled in-band and original-gate paths agree in all 14 corresponding pairs. The aligned midpoint has 45 rejections with identical ideal commands. All six estimator predicate pairs have 45 changed commands but retain a departure. These facts isolate the selected implementation contrast, rather than establish a generally sufficient horizon or backup policy.

In every retained bias cell, all 30 active biased packets are innovation-rejected. Each dropout cell records six missing packets. The estimator-case first-exit bracket is [98.235595703125, 98.23583984375] seconds, before the predeclared 100-second fault onset. Thus those injected faults cannot explain the first departure in these new cases. They supply packet-handling and later-continuation diagnostics, not an identified first-exit fault effect. No fault window was moved after these outcomes.

Decision CPU and wall times were measured on the local host during bounded parallel execution. They are observational costs, not worst-case execution times, deadline guarantees or an isolated hardware benchmark. All new geometric prediction decisions resolved in this execution; offline boundary ambiguity is still recorded even where the overall episode outcome is conclusive.
