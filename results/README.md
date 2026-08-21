# Results

`baseline.json` is generated from the five v0.1 scenarios using:

```bash
kri-space-lab benchmark scenarios/*.json --output results/baseline.json
```

The file is checked in to make behavioural changes visible during review. It is a deterministic
software baseline, not flight evidence and not a statistical research result.

Per-run evidence logs (`*.jsonl`) are ignored by Git because they are generated artifacts.
