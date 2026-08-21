# Experiment 001

## Runtime assurance under representative spacecraft-autonomy faults

### Question

Does a learned proximity-operations policy behave more safely when its commands are mediated by an
independent runtime-assurance monitor and deterministic fallback controller?

### Configurations

- `deterministic`: deterministic reference controller, no additional runtime gate;
- `learned`: learned imitation policy with direct command authority;
- `protected`: the same learned policy behind the KRI runtime-assurance monitor.

### Fault campaign

The v0.1 campaign contains five deterministic scenarios:

1. nominal approach;
2. range-sensor bias;
3. navigation sensor dropout;
4. simulated single-event upset that alters one learned-policy weight;
5. temporary actuator degradation.

### Metrics

The benchmark records mission completion, collision, unsafe-state exposure, safety interventions,
recovery after a fault, final relative state, and remaining propellant.

### Reproduce

```bash
kri-space-lab benchmark scenarios/*.json --output results/baseline.json
```

### v0.1 baseline

The checked-in baseline is a functional regression result, not a statistically meaningful scientific
claim. Across the five scenarios:

| Controller | Successes | Collisions | Unsafe-state steps |
| --- | ---: | ---: | ---: |
| Deterministic | 4 / 5 | 0 | 46 |
| Learned | 4 / 5 | 1 | 54 |
| Protected learned policy | 5 / 5 | 0 | 0 |

The protected policy invokes the safety layer frequently after model-integrity failure because the
monitor keeps the system in deterministic fallback once the expected model hash no longer matches.

### Interpretation

This baseline only demonstrates that the software components are wired coherently enough to support a
research programme. It does **not** establish that the KRI architecture is superior in realistic
spaceflight conditions. The next research step is a stochastic campaign with calibrated sensor noise,
combined faults, higher-fidelity relative dynamics, uncertainty calibration, and repeated trials.

### Relationship to KRI-STD-001

This experiment directly exercises the architecture described in KRI-STD-001 §§4.1, 4.4, 5.1 and
5.2, while providing only partial evidence for §4.2 and §4.3. See
[`kri-std-001-mapping.md`](kri-std-001-mapping.md) for the precise limitations.
