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
