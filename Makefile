.PHONY: install test lint benchmark verify

install:
	python -m pip install -e '.[dev]'

test:
	pytest

lint:
	ruff check .

benchmark:
	kri-space-lab benchmark scenarios/*.json --output results/baseline.json

verify:
	kri-space-lab verify-gate
