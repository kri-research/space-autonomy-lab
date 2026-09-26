# Observation-derived uncertainty for KRI Space Autonomy

SA02 adds a bounded-error, observation-to-set layer to the existing research phase.
It accepts the SA01 range/bearing packet interface and applied command history,
retains persistent common/channel bias hypotheses, and constructs an explicitly
outer state representation at decision or queued application time. It is simulation
research software, not an operational sensor calibration or flight estimator.

## Run the checked implementation

From a complete Git clone with all source-history branches, CPython 3.13.5 and an
isolated environment, run from `studies/information-aware-assurance-v1/`:

```sh
python3.13 -m venv /tmp/kri-sa02-env
. /tmp/kri-sa02-env/bin/activate
python -m pip install -r requirements-dev.txt
python -m pytest -c pyproject.toml --confcutdir=. sa02_tests
python -m ruff check sa02 sa02_tests
python -m ruff format --check sa02 sa02_tests
python -m sa02.artifact verify sa02/recorded --replay
# Optional new engineering execution; the directory must not exist.
python -m sa02.artifact run --output /tmp/kri-sa02-new-attempt
# SA01 remains separately reproducible, unchanged.
python -m iaa.artifact verify recorded_sa01_final --replay
```

The new run executes ten named engineering cases only. It does not rerun earlier
scientific campaigns or start SA03. All evidence is source-bound. Fresh timing
samples are host measurements, not deterministic replay outputs; only their original
recorded identities are verified. Source commits remain reachable through the retained
SA02 feature branch after a protected squash merge.

## Interfaces and evidence

`model.py` defines latent fault hypotheses, resource limits, applied-history segments
and outer-only estimates. `estimator.py` implements causal updates and delayed-packet
replay. `bridge.py` is the positive-only mathematical adapter to the unchanged SA01
checker. `oracle.py` provides structurally separate exact small-linear references and
rational matrix-tail HCW point checks.
`packet_fixtures.py` supplies explicit packet replays, including inconsistency and a
nonempty false exclusion when an assumed sensor bound is deliberately violated.
`runtime.py` integrates the estimator in a separately identified baseline loop.

Read [MATHEMATICS.md](MATHEMATICS.md) before crediting any bound. `source-map.json`
identifies reused source, `protocol.json` fixes the engineering scope, and `recorded/`
contains inputs, full traces, comparisons, small reference outcomes and separate host
timing receipts. Numerical truth appears only in simulator/evaluation records, never
in the observer or its validity tests. [RESULTS.md](RESULTS.md) interprets the actual
outcomes without converting a small engineering set into a population comparison.

The estimator uses constant latent offsets and the explicitly permitted fault windows.
It does not cover arbitrary bias drift, arbitrary unknown switches, unbounded noise,
uncalibrated real sensors or different dynamics merely because a packet is well formed.
An empty measurement consistency set is a model/data conflict, not physical impossibility.
All returned boxes remain outer enclosures; even their corners are not certified
observation-compatible witnesses. Negative common-action input is deliberately rejected.

The implementation measures observer-call host latency, while the simulation retains
SA01's declared 50 ms decision-path model. These quantities are separate. No target
processor, worst-case latency, complete hardware path or energy benefit is established.
The physical protection obligation remains a finite prefix plus a three-second coast,
with explicit expiry. It is not full recovery or indefinitely safe stopping.

## Preservation and next boundary

All SA01 executable files, frozen protocols and both recorded directories remain intact.
New results use their own names and source commit. E001-E005, property-alignment studies,
historical releases, manuscript, website, standard PDF and checklist are unchanged.
The next stage may investigate information-aware decisions within this stated contract.
Its work is not executed or assumed successful here. Real sensor bounds, mission-engineer
review, arbitrary fault schedules and target hardware remain separate dependencies.
