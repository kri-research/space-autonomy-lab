# Space Autonomy Lab demos

The checked-in demo bundles are deterministic views of the public controller/fault/report harness.
They are intended for inspection and integration testing, not as substitutes for the frozen
scientific campaigns.

## Bundles

- `rpo-benchmark/`: direct-measurement one-dimensional harness.
- `rpo-estimated/`: the same controller through the frozen-estimator product profile.

Each bundle contains `index.html`, `demo.md`, `demo.json`, and `bundle-manifest.json`.

Rebuild from the repository root:

```bash
uv run python -m kri_space_autonomy.demo build
uv run python -m kri_space_autonomy.demo build --navigation-profile estimated
```

The generated payload embeds frozen aggregate evidence from Experiments 002 and 003 because those
campaigns share the one-dimensional product-harness boundary. Experiments 004 and 005 use different
dynamics and physical-evaluation boundaries and therefore remain separate research records.

See:

- [public demo guide](../docs/public-rpo-demo.md)
- [benchmark guide](../docs/benchmark-guide.md)
- [Experiment 004 final result](../docs/experiment-004-results.md)
- [Experiment 005 final closeout](../docs/experiment-005-confirmatory-closeout.md)

A demo `PASS` means only that the checked-in example criteria passed in this harness. It is not a
flight-safety, certification, or KRI-STD-001 conformance claim.
