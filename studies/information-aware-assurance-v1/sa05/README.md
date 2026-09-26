# Prospective finite-manoeuvre evaluation

SA05 enhances KRI's existing Space Autonomy research with independently integrated
nonlinear Basilisk dynamics and a prospectively frozen comparison of four existing
sensing schedules. Read MATHEMATICS.md and protocol.json for scope. Current work
remains software-level research with explicitly simulated timing and energy.

## Isolated environment

Use a full-history clone including retained source branches and CPython 3.13.5.
From studies/information-aware-assurance-v1:

```sh
python3.13 -m venv /tmp/kri-sa05-env
. /tmp/kri-sa05-env/bin/activate
python -m pip install --only-binary=:all: -r sa05/requirements.txt
python -m pytest -c pyproject.toml --confcutdir=. sa05_tests
python -m ruff check sa05 sa05_tests
python -m ruff format --check sa05 sa05_tests
```

The older stages retain their separate dependency contracts and test invocations.
No old source or evidence is replaced. Analysis, plotting and replay code live in
this directory; all actual measurement/trajectory and host-evidence limits are
stated explicitly. The framework performs no physical actuation or external outreach.

## Research records

Development inputs are a separate, exposed pilot. A frozen held-out evaluation
must name the public deposit commit and use a new output directory. A routine
verification never starts a new campaign or repeats host timing measurements.
After the result is deposited, verification is:

```sh
python -m sa05.artifact verify sa05/recorded
python -m sa05.artifact verify sa05/recorded --sample
# Complete numerical reproduction of every successfully executed frozen cell:
python -m sa05.artifact verify sa05/recorded --replay
```

Numerical replay requires the same decisions and event categories with the declared
potential tolerance; content hashes bind the original evidence exactly. Fresh host
times cannot reproduce identically. Plot/table regeneration is checked from stored
results. Numerical simulation and repeated computational checks are not physical or
external validation. The prospective deposit and actual outcome interpretation will
be identified in RESULTS.md, without rewriting the frozen protocol or earlier work.
