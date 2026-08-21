# Contributing

Contributions should strengthen reproducibility, fault coverage, runtime-assurance experiments,
or spacecraft-autonomy research.

Before opening a pull request:

1. Keep experiments deterministic unless randomness is part of the stated research question.
2. Add or update tests.
3. Run `ruff check .` and `pytest`.
4. State which experiment, metric, or KRI-STD-001 requirement the change supports.
5. Do not describe simulation evidence as flight qualification or regulatory conformance.
