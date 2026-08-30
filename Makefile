.PHONY: install test lint benchmark verify pilot-freeze pilot-run pilot-analyze amendment-validate amendment-freeze amendment-run amendment-analyze amendment-scan confirmatory-validate confirmatory-freeze confirmatory-verify-freeze confirmatory-materialize-seeds confirmatory-run confirmatory-analyze confirmatory-verify-results confirmatory-scan

install:
	uv sync --frozen --extra dev

test:
	uv run pytest

lint:
	uv run ruff check .

benchmark:
	uv run kri-space-lab benchmark scenarios/*.json --output results/baseline.json

verify:
	uv run kri-space-lab verify-gate

pilot-freeze:
	uv run python -m kri_space_autonomy.experiment_002.workflow freeze

pilot-run:
	uv run python -m kri_space_autonomy.experiment_002.workflow run

pilot-analyze:
	uv run python -m kri_space_autonomy.experiment_002.workflow analyze

amendment-validate:
	uv run python -m kri_space_autonomy.experiment_002b.workflow validate

amendment-freeze:
	uv run python -m kri_space_autonomy.experiment_002b.workflow freeze

amendment-run:
	uv run python -m kri_space_autonomy.experiment_002b.workflow run

amendment-analyze:
	uv run python -m kri_space_autonomy.experiment_002b.workflow analyze

amendment-scan:
	uv run python -m kri_space_autonomy.experiment_002b.workflow release-scan

confirmatory-validate:
	uv run python -m kri_space_autonomy.experiment_002_confirmatory.workflow validate

confirmatory-freeze:
	uv run python -m kri_space_autonomy.experiment_002_confirmatory.workflow freeze

confirmatory-verify-freeze:
	uv run python -m kri_space_autonomy.experiment_002_confirmatory.workflow verify-freeze

confirmatory-materialize-seeds:
	uv run python -m kri_space_autonomy.experiment_002_confirmatory.workflow materialize-seeds

confirmatory-run:
	uv run python -m kri_space_autonomy.experiment_002_confirmatory.workflow run

confirmatory-analyze:
	uv run python -m kri_space_autonomy.experiment_002_confirmatory.workflow analyze

confirmatory-verify-results:
	uv run python -m kri_space_autonomy.experiment_002_confirmatory.workflow verify-results

confirmatory-scan:
	uv run python -m kri_space_autonomy.experiment_002_confirmatory.workflow release-scan
