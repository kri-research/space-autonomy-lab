.PHONY: install test lint benchmark verify pilot-freeze pilot-run pilot-analyze

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
