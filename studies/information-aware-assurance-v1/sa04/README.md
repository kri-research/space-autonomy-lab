# Deadline-aware execution for KRI Space Autonomy

SA04 adds a bounded JSON service, smaller realized-action checker, context-bound
expiring gate, causal replay and separate host measurements. The unchanged SA03
uncertainty-triggered baseline and decision-aware candidate supply proposals.
The checker reconstructs SA02 uncertainty from received packets and verifies the
proposed command through a finite coast. No physical I/O backend is present.

Read [MATHEMATICS.md](MATHEMATICS.md) for the new [700,710] ms initiation window,
fixed 1200 ms command end, 4200 ms expiry, initial entry assumptions and trusted base.
Read RESULTS.md for actual timing and adverse outcomes. Initialization is offline
simulation preparation, not permission to freeze a live spacecraft.

## Reproduction

Use a full-history clone including retained source branches, CPython 3.13.5 and an
isolated environment. From `studies/information-aware-assurance-v1/`:

```sh
python3.13 -m venv /tmp/kri-sa04-env
. /tmp/kri-sa04-env/bin/activate
python -m pip install -r requirements-dev.txt
python -m ruff check .
python -m ruff format --check .
python -m pytest -c pyproject.toml --confcutdir=. sa04_tests
python -m sa04.artifact verify sa04/recorded --replay
```

Verification recomputes every deterministic integration fixture. Recorded host samples
are checked for identity/accounting, not expected to repeat. A new bounded execution
can be made with `python -m sa04.artifact run --output /tmp/kri-sa04-new-attempt`.
Output must not exist and must be outside Git checkouts. This runs the prospective
host protocol as well as simulated fixtures, without overwriting existing evidence.

Run the earlier `tests`, `sa02_tests` and `sa03_tests` in separate pytest invocations;
their existing module basenames overlap. Their original artifact/replay commands are
unchanged. No earlier scientific campaign is restarted.

## Component map

| Module | Responsibility |
| --- | --- |
| wire.py and legacy.py | Strict extension of the original execution protocol |
| compute.py | Observation reconstruction, planner adapter, single-action/window check |
| gate.py | Binding, initiation, fixed termination, invalidation and expiry |
| service.py and transport.py | Role-specific subprocess IPC and real timeouts |
| trace.py and fixtures.py | Read-only semantic replay and simulated fault fixtures |
| host.py and host-protocol.json | Bounded actual host timing/resource evidence |
| artifact.py | Complete record and actual Git-blob/mode verification |

This is a research component, with no operational safety, flight qualification,
standard-conformance or full-recovery claim. A negative timing result can complete
SA04 while leaving real-time deployment unsupported. Website, publication page,
standard PDF, Excel checklist and existing manuscript remain unchanged. SA05 is not
executed by this task.
