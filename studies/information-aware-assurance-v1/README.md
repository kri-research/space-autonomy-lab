# Information-aware assurance reference phase

SA01 enhances KRI's existing Space Autonomy programme with a simulation-only
sensing-to-actuation reference loop. This is an engineering foundation, not a
new safety or active-sensing result. Existing experiments and property-alignment
evidence remain untouched. The [current research index](../README.md) separates
the phases and their claims.

## Run and reproduce

Use a complete Git clone including history, CPython 3.13.5, and an isolated
environment. Runtime has no third-party package dependency.

```sh
cd studies/information-aware-assurance-v1
python3.13 -m venv /tmp/kri-sa01-env
. /tmp/kri-sa01-env/bin/activate
python -m pip install -r requirements-dev.txt
python -m pytest -c pyproject.toml --confcutdir=. tests
python -m ruff check .
python -m ruff format --check .
python -m iaa.artifact verify recorded_sa01_final --replay
# A new output path outside the clone is required; never overwrite an attempt.
python -m iaa.artifact run --output /tmp/kri-sa01-new-attempt
```

The last command executes only the nine small named engineering fixtures in
`engineering-protocol.json`, never earlier campaigns or future held-out trials.
It requires committed stage sources. `verify --replay` recomputes all summaries
and event traces and compares them exactly. Plain `verify` checks content, complete
file membership, current source hashes and the actual Git blobs at the recorded
source revision. It also checks the manifest against the committed recorded manifest
in the chosen checkout, so co-editing a payload and its checksum does not pass.
Verification is for the published fixture set or an exact copy; a newly generated
attempt has its own identity and is retained separately. A checksum alone does
not validate the model or experiment.

`recorded_sa01_final/` contains the current synthetic event traces and outcome summaries. Interpretation
is in [RESULTS.md](RESULTS.md). All failed, unsupported, late and contrary cases
remain included. This fixed engineering selection supports no efficacy ranking,
confidence interval, population safety probability or operational fault frequency.

## Components

| Module | Purpose |
| --- | --- |
| `iaa/types.py` | Versioned packets, enclosures, commands, checking results and execution records. |
| `iaa/plant.py` | Numerical HCW truth and range/bearing generation with explicit causal faults. |
| `iaa/controller.py` | Packet-only PD proposal with approximate finite-difference velocity. |
| `iaa/enclosure.py` | Exact-rational coarse continuous inclusion and property checks. |
| `iaa/assurance.py` | Prior-envelope finite-prefix checks and simulation-only timed command leases. |
| `iaa/runtime.py` | Event ordering, packet delivery, modeled work accounting and separate evaluation. |
| `iaa/fixtures.py` | Nine named engineering inputs, including contrary cases. |
| `iaa/artifact.py` | Bounded execution and source-bound deterministic replay. |

Read [CONTRACT.md](CONTRACT.md) for the physical definitions, assumptions, timeline,
protective entry/expiry semantics and inclusion argument, and [related-work.md](related-work.md)
for primary sources, access limits and reuse decisions. Source pins are in `source-map.json`.

## What remains unsupported

SA01 propagates a supplied initial enclosure. It does not infer validated state
sets from sensors, calibrate sensors or diagnose every fault. Measurement-based
uncertainty is SA02. Information-aware sensing/control selection is SA03. Existing
active-sensing research is explicitly acknowledged rather than renamed as new.
The checker only supports a finite command prefix plus a three-second coast. It
makes no invariant-set, full-recovery or indefinitely safe-stop claim.

Latency and energy are declared simulation models. No processor deadline, worst-case
execution time, physical watchdog, sensor/actuator response, clock accuracy or
hardware energy has been measured. The same inclusion code supports online checks
and offline evaluation; its validation is not an independent physical replication.
The command sink is an internal simulator, not a malicious-plugin security boundary.
No existing journal files, website, standard PDF, checklist, historical tags or
scientific inputs are modified by this phase.

## External use-case review still needed

A navigation/mission engineer should examine the circular-chief planar reduction,
standoff-box geometry, initial knowledge, fault model, sensor geometry and feasible
rates, command authority, three-second coast entry/exit, and the proposed timing
and resource envelope. Actual calibration and hardware access must be established
before they support mission-facing claims. No invitation or external review has
been performed by SA01. This dependency does not prevent using the engineering loop.

## Retained first execution and interface correction

The first completed engineering execution remains byte-for-byte in `recorded/`,
with its original source and manifest. It predates the scope/expiry interface
correction. Before final integration, two adversarial checks found that an
unsupported checking scope and an overextended coast-expiry value could be
accepted by the internal sink. The current implementation rejects both. No
change was made to the physical contract, fixture population, controller, modeled
budgets or endpoint definitions to improve outcomes. The separately identified
current execution is `recorded_sa01_final/`; read RESULTS.md for its comparison.

To inspect the first execution, use a separate full-history checkout at the
record commit `748635867f3e2801aa293c61f305953262dbc1f1` and run its documented
`verify recorded --replay` there. That older implementation is retained evidence,
not the current interface. Current verification deliberately rejects an old
manifest paired with new source.
