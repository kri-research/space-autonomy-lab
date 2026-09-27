# Post-outcome numerical verification

This directory is separate from the prospectively frozen policy, analysis and
experiment sources. It cannot retune or rerun the original campaign. The copied
`postflight.py` is byte-identical to the read-only script that produced
`independent-numerical-audit.json` after the original 448 method runs.

The audit re-integrates every actual command schedule using the separately written
nonlinear rotating-frame DOP853 reference. It does not import the Basilisk adapter,
its adjudicator, the controller, or the original primary analysis. It separately
recomputes continuous numerical containment, goal dwell and acquisition, and checks
the recorded sample states. Shared model constants and numerical allowances remain
explicit. This is computational corroboration on one host, not outside replication,
physical validation or a universal floating-point error proof.

From `studies/information-aware-assurance-v1/` in the documented SA05 environment:

```sh
python -m sa05_validation.verify
python -m pytest -c pyproject.toml --confcutdir=. sa05_validation
# Fresh read-only numerical audit; destination must not already exist.
python -m sa05_validation.postflight . sa05/recorded /tmp/kri-sa05-new-numerical-audit.json
```

`verify` checks the committed original artifact, source bindings, complete audit
membership, numerical thresholds and endpoint correspondence. It does not rerun the
independent ODE. The last command does, retaining a new output without overwriting
the original audit. No hardware measurements or new experimental units are created.
